import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import re
import portalocker
from urllib.parse import urlsplit

import httpx
import uvicorn
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from . import VERSION
from .registry import atomic, encode, Registry
from .security import SafeError, vault_put, auth_target, auth_secret, token_digest, validate_url


def bootstrap(config_path,helper,bws,port=8769,client_paths=None,host_id='local-pilot'):
    path=Path(config_path).resolve()
    if path.exists():raise SafeError('Runtime already configured. Existing identity keys were preserved.')
    if not Path(helper).is_absolute() or not Path(helper).is_file():raise SafeError('Build/install the native helper first.')
    path.parent.mkdir(parents=True,exist_ok=True)
    from .doctor import identity
    from .registry import ID
    if not ID.fullmatch(host_id):raise SafeError('Use a stable lowercase host ID.')
    cfg={'schema_version':1,'host_id':host_id,'runtime_identity':identity(),'data_dir':str(path.parent),'url':f'http://127.0.0.1:{port}/mcp',
        'helper_executable':str(Path(helper).resolve()),'bws_executable':str(Path(bws).resolve()),'identities':{},'client_paths':client_paths or {}}
    for identity in ('admin','codex','claude'):
        value=secrets.token_urlsafe(48)
        target=auth_target(path.parent,identity)
        if os.name=='nt':
            vault_put(target,value)
            location={'vault_target':target}
        else:
            secret_path=path.parent/'secrets'/identity
            secret_path.parent.mkdir(mode=0o700,exist_ok=True)
            atomic(secret_path,value.encode());secret_path.chmod(0o600)
            location={'secret_file':str(secret_path)}
        cfg['identities'][identity]={**location,'sha256':token_digest(value),'services':[]}
    atomic(path,encode(cfg))
    return {'configured':str(path),'url':cfg['url'],'version':VERSION,'credentials':'OS vault' if os.name=='nt' else 'restricted local secret files'}


async def management(config_path,body):
    cfg=json.loads(Path(config_path).read_bytes())
    async with httpx.AsyncClient(timeout=60,follow_redirects=False,trust_env=False) as client:
        response=await client.post(cfg['url'].removesuffix('/mcp')+'/admin',json=body,
                                  headers={'Authorization':'Bearer '+auth_secret(cfg,'admin')})
        result=response.json()
        if response.status_code!=200:raise SafeError(result.get('error','Gateway management request failed.'))
        return result


async def bridge(config_path,identity):
    cfg=json.loads(Path(config_path).read_bytes())
    if identity=='admin' or identity not in cfg['identities']:raise SafeError('Choose a configured client identity.')
    validate_url(cfg['url'])
    server=Server('ECPA gateway bridge',version=VERSION)
    @server.list_tools()
    async def tools():
        # Each operation authenticates anew, so key rotation/revocation is immediate.
        async with httpx.AsyncClient(headers={'Authorization':'Bearer '+auth_secret(cfg,identity)},timeout=60,follow_redirects=False,trust_env=False) as client:
            async with streamable_http_client(cfg['url'],http_client=client) as streams:
                async with ClientSession(streams[0],streams[1]) as session:
                    await session.initialize()
                    return (await session.list_tools()).tools
    @server.call_tool(validate_input=False)
    async def call(name,arguments):
        try:
            async with httpx.AsyncClient(headers={'Authorization':'Bearer '+auth_secret(cfg,identity)},timeout=60,follow_redirects=False,trust_env=False) as client:
                async with streamable_http_client(cfg['url'],http_client=client) as streams:
                    async with ClientSession(streams[0],streams[1]) as session:
                        await session.initialize()
                        return await session.call_tool(name,arguments or {})
        except Exception:
            return types.CallToolResult(isError=True,content=[types.TextContent(type='text',text='Gateway unavailable or access denied. Check Connections Manager runtime status.')])
    async with stdio_server() as streams:
        await server.run(*streams,server.create_initialization_options())


def scaffold(output):
    directory=Path(output).resolve()
    directory.mkdir(parents=True,exist_ok=True)
    if any(directory.iterdir()):raise SafeError('Scaffold destination must be empty.')
    atomic(directory/'server.py',b'''from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
app = FastMCP("reviewed-service-starter")
@app.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
def status() -> dict:
    """Read-only starter; no network, files or credentials until explicitly implemented."""
    return {"status": "ready", "synthetic": True}
if __name__ == "__main__": app.run()
''')
    atomic(directory/'requirements.txt',b'mcp==1.30.0\n')
    atomic(directory/'service.json',encode({'id':'my-service','name':'My service','kind':'stdio','enabled':False,
        'transport':{'command':sys.executable,'args':[str(directory/'server.py')],'package':'reviewed-service-starter','version':'0.1.0'},
        'credential_refs':[],'allowed_tools':[]}))
    atomic(directory/'README.md',b'''# Read-only MCP starter

Run server.py with Python containing mcp==1.30.0. Import service.json into Connections
Manager, test initialize/list tools, review status, then publish. The SDK manages MCP.

Before connecting an API: review official API documentation/OpenAPI, choose explicit
read operations and a fixed destination, map a secret reference to its required
environment variable, disable redirects, enforce TLS/time/response limits and filter
sensitive output. Do not expose an arbitrary URL/method tool. A key cannot identify
an API. Tool annotations are descriptions; the implementation must enforce reads.

Add contract tests with fake HTTP responses that reject non-GET methods, unknown
operations, malformed arguments and credential-bearing errors. Keep live credentials
out of tests. No automatic OpenAPI execution or installation is performed.
''')
    atomic(directory/'test_contract.py',b'''import unittest
from server import status
class Contract(unittest.TestCase):
    def test_read_only_starter(self):
        self.assertEqual(status(), {"status": "ready", "synthetic": True})
if __name__ == "__main__": unittest.main()
''')
    return {'scaffold':str(directory)}


def main():
    parser=argparse.ArgumentParser(description='ECPA managed MCP gateway')
    parser.add_argument('--config',default=str(Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'ECPA/connections-manager/gateway-runtime.json'))
    sub=parser.add_subparsers(dest='action',required=True)
    init=sub.add_parser('init');init.add_argument('--helper',required=True);init.add_argument('--bws',required=True);init.add_argument('--port',type=int,default=8769)
    init.add_argument('--codex-config');init.add_argument('--claude-config');init.add_argument('--native-catalogue');init.add_argument('--host-id',default='local-pilot')
    serve=sub.add_parser('serve');serve.add_argument('--bind',default='127.0.0.1');serve.add_argument('--private-listener',action='store_true')
    br=sub.add_parser('bridge');br.add_argument('--identity',required=True)
    admin=sub.add_parser('admin');admin.add_argument('--request-file',help='JSON request file; defaults to stdin')
    sc=sub.add_parser('scaffold');sc.add_argument('--output',required=True)
    oa=sub.add_parser('oauth-login');oa.add_argument('--profile',required=True)
    job=sub.add_parser('run-wrangler');job.add_argument('--profile',required=True);job.add_argument('--workspace',required=True);job.add_argument('--operation',default='verify')
    sub.add_parser('bootstrap-bws')
    doctor=sub.add_parser('doctor');doctor.add_argument('--network',action='store_true');doctor.add_argument('--protocol',action='store_true')
    ci=sub.add_parser('client-init');ci.add_argument('--url',required=True);ci.add_argument('--identity',required=True)
    grant=sub.add_parser('grant-client');grant.add_argument('--identity',required=True);grant.add_argument('--sha256',required=True);grant.add_argument('--service',action='append',required=True);grant.add_argument('--group',action='append',default=[]);grant.add_argument('--project',action='append',default=[])
    revoke=sub.add_parser('revoke-client');revoke.add_argument('--identity',required=True)
    args=parser.parse_args()
    logging.basicConfig(level=logging.CRITICAL)
    try:
        if args.action=='init':
            paths={k:v for k,v in {'codex':args.codex_config,'claude':args.claude_config,'native':args.native_catalogue}.items() if v}
            print(json.dumps(bootstrap(args.config,args.helper,args.bws,args.port,paths,args.host_id)))
        elif args.action=='doctor':
            from .doctor import report
            result=asyncio.run(report(args.config,args.network,args.protocol));print(json.dumps(result,indent=2));raise SystemExit(0 if result['ready'] else 1)
        elif args.action=='client-init':
            from .identities import client_init
            print(json.dumps(client_init(args.config,args.url,args.identity)))
        elif args.action in ('grant-client','revoke-client'):
            from .identities import grant_client,revoke_client
            result=grant_client(args.config,args.identity,args.sha256,args.service,args.group or ['default'],args.project) if args.action=='grant-client' else revoke_client(args.config,args.identity)
            print(json.dumps(result))
        elif args.action=='serve':
            from .app import create_app
            cfg=json.loads(Path(args.config).read_bytes())
            if args.bind not in ('127.0.0.1','::1') and not args.private_listener:raise SafeError('Non-loopback binds require explicit private-listener acknowledgement and an authenticated TLS/Tailscale boundary.')
            uvicorn.run(create_app(args.config),host=args.bind,port=urlsplit(cfg['url']).port or 8769,log_level='critical',log_config=None,access_log=False,proxy_headers=False)
        elif args.action=='bridge':asyncio.run(bridge(args.config,args.identity))
        elif args.action=='scaffold':print(json.dumps(scaffold(args.output)))
        elif args.action=='bootstrap-bws':
            from .security import user_env
            cfg=json.loads(Path(args.config).read_bytes())
            target=auth_target(cfg['data_dir'],'bws-machine')
            with portalocker.Lock(str(args.config)+'.lock',timeout=3):
                cfg=json.loads(Path(args.config).read_bytes())
                vault_put(target,user_env('BWS_ACCESS_TOKEN'));cfg['bws_vault_target']=target
                atomic(Path(args.config),encode(cfg))
            print('Bitwarden bootstrap saved in this runtime identity\'s Windows vault. No token was printed.')
        elif args.action in ('oauth-login','run-wrangler'):
            cfg=json.loads(Path(args.config).read_bytes());service=Registry(cfg['data_dir']).selected(args.profile)
            if args.action=='oauth-login':
                from .oauth import login
                result=asyncio.run(login(service,cfg))
            else:
                from .jobs import run_wrangler
                result=asyncio.run(run_wrangler(service,cfg,args.workspace,args.operation))
            print(json.dumps(result))
        else:
            raw=Path(args.request_file).read_text() if args.request_file else sys.stdin.read(65537)
            if len(raw)>65536:raise SafeError('Management request too large.')
            print(json.dumps(asyncio.run(management(args.config,json.loads(raw))),ensure_ascii=False))
    except SafeError as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
    except Exception:
        print('Gateway operation failed; internal details were suppressed.',file=sys.stderr);raise SystemExit(1)

if __name__=='__main__':main()
