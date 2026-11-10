"""Read-only readiness checks; never dump environment, config or command output."""
import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from .security import auth_secret, token_digest, vault_get, user_env, clean_env


def identity():
    if os.name=='nt':
        import win32api, win32security
        sid=win32security.GetTokenInformation(win32security.OpenProcessToken(win32api.GetCurrentProcess(),8),1)[0]
        return win32security.ConvertSidToStringSid(sid)
    return 'uid:'+str(os.getuid())


async def report(config_path,network=False,protocol=False):
    checks=[]
    def add(name,status,detail):checks.append({'check':name,'status':status,'detail':detail})
    add('Python','pass' if sys.version_info[:2]==(3,13) else 'warning',platform.python_version()+'; tested baseline 3.13.6, supported >=3.12')
    for package,version in [('mcp','1.30.0'),('uvicorn','0.54.0'),('tomlkit','0.15.0'),('portalocker','3.2.0'),('json5','0.12.1')]:
        try:
            actual=importlib.metadata.version(package)
            add(package,'pass' if actual==version else 'warning',actual+'; tested '+version)
        except importlib.metadata.PackageNotFoundError:add(package,'fail','Missing dependency')
    path=Path(config_path).resolve()
    parent=path.parent
    while not parent.exists():parent=parent.parent
    free=shutil.disk_usage(parent).free//(1024**3)
    add('disk','pass' if free>=2 else 'fail',str(free)+' GiB free; reserve at least 2 GiB for this worker, more for other services')
    current=identity()
    add('identity','pass',current)
    try:cfg=json.loads(path.read_bytes())
    except Exception:
        add('configuration','fail','Runtime is not initialized or its config is unreadable')
        return {'ready':False,'checks':checks}
    expected=cfg.get('runtime_identity')
    add('task identity','pass' if expected==current else 'warning' if not expected else 'fail',
        'Matches bootstrap identity' if expected==current else 'Run init/bootstrap and the task as the same dedicated Windows account')
    for key,label in [('helper_executable','Portainer helper'),('bws_executable','Bitwarden CLI')]:
        target=Path(cfg.get(key,''))
        add(label,'pass' if target.is_absolute() and target.is_file() else 'fail','Installed' if target.is_file() else 'Missing configured executable')
    # Parse only a version number; suppress raw executable diagnostics.
    bws=cfg.get('bws_executable')
    if bws and Path(bws).is_file():
        try:
            p=await asyncio.create_subprocess_exec(bws,'--version',env=clean_env(),stdout=asyncio.subprocess.PIPE,stderr=subprocess.DEVNULL)
            out,_=await asyncio.wait_for(p.communicate(),5)
            match=re.search(rb'\b\d+\.\d+\.\d+\b',out[:200])
            v=match.group().decode() if match else 'unrecognized'
            add('bws version','pass' if v=='2.1.0' else 'warning',v+'; tested 2.1.0')
        except Exception:add('bws version','fail','Could not run CLI version check')
        finally:
            if 'p' in locals() and p.returncode is None:p.kill();await p.wait()
    try:
        value=auth_secret(cfg,'admin')
        valid=token_digest(value)==cfg['identities']['admin']['sha256'];del value
        add('management credential','pass' if valid else 'fail','Accessible and matched' if valid else 'Key mismatch')
    except Exception:add('management credential','fail','Unavailable under this process identity')
    try:
        if cfg.get('bws_vault_target'):value=vault_get(cfg['bws_vault_target'])
        elif cfg.get('bws_token_file'):value=Path(cfg['bws_token_file']).read_text().strip()
        else:value=user_env('BWS_ACCESS_TOKEN')
        available=bool(value);del value
        add('Bitwarden bootstrap','pass' if available else 'fail','Present; grants/expiry require a service connection test')
    except Exception:add('Bitwarden bootstrap','warning','Not configured for this identity; needed for Bitwarden profiles')
    url=urlsplit(cfg['url']);port=cfg.get('listen_port') or url.port or 8769
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=2):pass
        add('loopback listener','pass','Port '+str(port)+' is accepting TCP; protocol check confirms ownership')
    except OSError:add('loopback listener','warning','Port '+str(port)+' is not listening; expected before startup')
    for name,exe in [('Tailscale','tailscale'),('Node (optional)','node'),('Git (optional)','git'),('PowerShell 7 (optional)','pwsh'),('T3 (optional runner)','t3')]:
        found=shutil.which(exe)
        add(name,'pass' if found else 'warning','Available on PATH' if found else 'Not on PATH; install only if required for this host role')
    if network:
        async with httpx.AsyncClient(timeout=8,trust_env=False,follow_redirects=False) as client:
            for host in ('vault.bitwarden.eu','vault.bitwarden.com'):
                try:
                    response=await client.head('https://'+host)
                    add('TLS '+host,'pass','Reachable (HTTP '+str(response.status_code)+'); no credentials sent')
                except Exception:add('TLS '+host,'warning','DNS/TLS/HTTPS unavailable')
    if protocol:
        try:
            selected=next(k for k in cfg['identities'] if k!='admin' and not cfg['identities'][k].get('revoked'))
            async with httpx.AsyncClient(headers={'Authorization':'Bearer '+auth_secret(cfg,selected)},timeout=10,trust_env=False,follow_redirects=False) as client:
                async with streamable_http_client(cfg.get('public_url',cfg['url']),http_client=client) as streams:
                    async with ClientSession(streams[0],streams[1]) as session:
                        await session.initialize();listing=await session.list_tools()
                        add('MCP handshake','pass',str(len(listing.tools))+' allowed tools; no service tools called')
        except Exception:add('MCP handshake','fail','Initialize/list tools failed; verify identity, URL, TLS and listener')
    return {'ready':not any(c['status']=='fail' for c in checks),'host_id':cfg.get('host_id'),'checks':checks,
        'limits':'This check does not prove reboot, sign-out persistence, upstream grants or another machine reachability.'}
