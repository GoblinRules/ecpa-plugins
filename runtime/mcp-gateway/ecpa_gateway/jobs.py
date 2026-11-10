"""Explicit local worker operations. This is not a scheduler or remote shell."""
import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import signal
import tempfile
import tomllib
import json5
from .security import SafeError, clean_env, resolve


def checked_workspace(service,config,workspace_id):
    workspace=config.get('workspaces',{}).get(workspace_id)
    if not workspace or workspace_id not in service.get('wrangler',{}).get('workspace_ids',[]):
        raise SafeError('Workspace is not assigned to this profile on this execution host.')
    root=Path(workspace).resolve()
    if not root.is_dir():raise SafeError('The selected workspace is not present on this runtime host. Sync it through the existing runner/workspace mechanism first.')
    return root


def check_wrangler_config(root,profile):
    settings=profile['wrangler']
    account=profile.get('account_id','')
    if not re.fullmatch('[0-9a-fA-F]{32}',account):raise SafeError('An explicit Cloudflare account ID is required.')
    selected=Path(settings.get('config_file','wrangler.jsonc'))
    if selected.is_absolute():raise SafeError('Wrangler configuration must be relative to the assigned workspace.')
    path=(root/selected).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise SafeError('Wrangler config must be a file inside the assigned workspace.')
    # .env variables and generated/delegated configs could override identity/endpoints.
    for parent in (path.parent,*path.parent.parents):
        if (parent/'.wrangler/deploy/config.json').exists():raise SafeError('Generated Wrangler config is present. Review it explicitly before using a managed profile.')
        for env in parent.glob('.env*'):
            if env.is_file():
                text=env.read_text(encoding='utf-8',errors='replace')
                if re.search(r'(?mi)^\s*(?:export\s+)?(?:CF_|CLOUDFLARE_|WRANGLER_|NODE_OPTIONS|HTTPS?_PROXY|ALL_PROXY)',text):
                    raise SafeError('Workspace/ancestor .env contains authentication or runtime overrides. Remove the conflict before running this profile.')
    try:
        raw=path.read_text(encoding='utf-8-sig')
        data=tomllib.loads(raw) if path.suffix=='.toml' else json5.loads(raw)
    except Exception:raise SafeError('Wrangler config cannot be parsed safely.') from None
    env_name=settings.get('environment')
    scoped=data.get('env',{}).get(env_name,{}) if env_name else {}
    for section in (data,scoped):
        if section.get('account_id') not in (None,'',account):raise SafeError('Wrangler config targets a different Cloudflare account. No command was started.')
        if section.get('build',{}).get('command'):raise SafeError('Custom build commands need a separate trusted job review before credentials are injected.')
    if env_name and env_name not in data.get('env',{}):raise SafeError('Selected Wrangler environment is not declared.')
    return path


async def run_wrangler(service,config,workspace_id,operation):
    if not service.get('enabled') or service.get('execution_host',config.get('host_id'))!=config.get('host_id'):
        raise SafeError('Profile is disabled or belongs to another execution host.')
    root=checked_workspace(service,config,workspace_id)
    path=check_wrangler_config(root,service)
    settings=service['wrangler']
    commands=settings.get('operations',{'verify':['whoami']})
    args=commands.get(operation)
    if not args or not isinstance(args,list) or not all(isinstance(a,str) for a in args):raise SafeError('Operation was not explicitly approved for this profile.')
    if any(a.split('=')[0] in ('--config','-c','--cwd','--env','-e','--profile','--account-id') for a in args):raise SafeError('Operation arguments cannot override the profile account, environment or workspace.')
    bindings=[b for b in service.get('credential_refs',[]) if b['kind']=='env' and b['name']=='CLOUDFLARE_API_TOKEN']
    if len(bindings)!=1:raise SafeError('Wrangler requires one CLOUDFLARE_API_TOKEN reference; OAuth MCP sessions cannot substitute for it.')
    token=await resolve(bindings[0]['reference'],config)
    environment=clean_env()
    # All conflicting/global Cloudflare credentials are absent from the allowlisted env.
    with tempfile.TemporaryDirectory(prefix='ecpa-wrangler-') as isolated:
        environment.update({'CLOUDFLARE_API_TOKEN':token,'CLOUDFLARE_ACCOUNT_ID':service['account_id'],
            'HOME':isolated,'USERPROFILE':isolated,'XDG_CONFIG_HOME':isolated,'APPDATA':isolated,
            'WRANGLER_SEND_METRICS':'false','WRANGLER_SEND_ERROR_REPORTS':'false','CI':'true',
            'CLOUDFLARE_AUTH_USE_KEYRING':'false'})
        node=settings['node_executable'];entry=settings['entrypoint']
        if not Path(node).is_absolute() or not Path(node).is_file() or not Path(entry).is_absolute() or not Path(entry).is_file():raise SafeError('Configure the installed Node executable and Wrangler entrypoint on this runtime host.')
        command=[node,entry,*args,'--config',str(path)]
        if settings.get('environment'):command+=['--env',settings['environment']]
        flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}
        child=await asyncio.create_subprocess_exec(*command,cwd=root,env=environment,stdin=subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT,**flags)
        try:
            async with asyncio.timeout(120):
                raw=b''
                while True:
                    chunk=await child.stdout.read(4096)
                    if not chunk:break
                    raw+=chunk
                    if len(raw)>1024*1024:raise SafeError('Job output exceeded its limit.')
                await child.wait()
            return {'profile':service['id'],'account_id':service['account_id'],'host':config['host_id'],
                    'workspace_id':workspace_id,'operation':operation,'exit_code':child.returncode,
                    'output':raw.decode(errors='replace').replace(token,'[REDACTED]')}
        except TimeoutError:raise SafeError('Wrangler job exceeded its time limit.') from None
        finally:
            if child.returncode is None:
                if os.name=='nt':
                    killer=await asyncio.create_subprocess_exec(str(Path(os.environ['SYSTEMROOT'])/'System32/taskkill.exe'),'/PID',str(child.pid),'/T','/F',stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
                    await killer.wait()
                else:
                    try:os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                if child.returncode is None:child.kill()
                await child.wait()
