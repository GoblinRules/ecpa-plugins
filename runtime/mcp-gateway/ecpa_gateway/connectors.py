"""Fresh upstream sessions per operation: no cross-client state or cached service keys."""
import asyncio
from contextlib import asynccontextmanager, AsyncExitStack
import hashlib
import json
import os
import sys
from datetime import timedelta

import httpx
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from .security import SafeError, clean_env, resolve
from .registry import validate_service, validate_schema
from . import oauth

oauth_locks={}


def tool_hash(tool):
    return hashlib.sha256(json.dumps(tool,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@asynccontextmanager
async def connection(service,config):
    validate_service(service)
    if service.get('execution_host',config.get('host_id')) != config.get('host_id'):
        raise SafeError('Profile belongs to a different execution host; no automatic remote execution is configured.')
    environment=clean_env()
    environment.update(service.get('public_env',{}))
    if service.get('service')=='cloudflare':environment['CLOUDFLARE_ACCOUNT_ID']=service['account_id']
    headers={}
    values=[]
    for binding in service.get('credential_refs',[]):
        secret=await resolve(binding['reference'],config)
        values.append(secret)
        if binding['kind']=='env':environment[binding['name']]=secret
        else:headers[binding['name']]=('Bearer '+secret if binding['name'].lower()=='authorization' else secret)
    kind=service['kind']
    if kind=='portainer':
        command=config['helper_executable']
        args=['portainer-mcp-env']
        environment['PORTAINER_URL']=service['url']
    elif kind=='sample':
        command=sys.executable
        args=['-m','ecpa_gateway.sample']
    elif kind=='stdio':
        command=service['transport']['command']
        args=service['transport'].get('args',[])
    async with AsyncExitStack() as stack:
        if kind=='http':
            kwargs={}
            if service.get('oauth'):
                # Serialize refreshes for the same resource/profile, not unrelated accounts.
                await stack.enter_async_context(oauth.profile_lock(service,config))
                kwargs={'auth':oauth.provider(service,config,values=values),'event_hooks':{'request':[oauth.request_guard(service)]}}
            client=await stack.enter_async_context(httpx.AsyncClient(headers=headers,timeout=30,follow_redirects=False,trust_env=False,**kwargs))
            streams=await stack.enter_async_context(streamable_http_client(service['url'],http_client=client))
        else:
            # Child diagnostics can contain credentials or prompt injection. Never echo them.
            null=stack.enter_context(open(os.devnull,'w'))
            streams=await stack.enter_async_context(stdio_client(StdioServerParameters(command=command,args=args,env=environment),errlog=null))
        session=await stack.enter_async_context(ClientSession(streams[0],streams[1],read_timeout_seconds=timedelta(seconds=30)))
        await session.initialize()
        yield session,values


def scrub(raw,values):
    text=json.dumps(raw)
    for value in values:
        text=text.replace(json.dumps(value)[1:-1],'[REDACTED]')
    if len(text)>2*1024*1024:raise SafeError('Connector response exceeded 2 MiB.')
    return json.loads(text)


async def discover(service,config):
    try:
        async with asyncio.timeout(45):
            async with connection(service,config) as (session,values):
                return await reviewed_tools(session,values)
    except SafeError:raise
    except Exception:
        raise SafeError('MCP initialize/tool discovery failed. Check installation, URL, credential access and transport.') from None


async def invoke(service,config,name,arguments):
    if not service.get('enabled') or name not in service.get('allowed_tools',[]):
        raise SafeError('Tool is not permitted by this service policy.')
    snapshot=next((t for t in service.get('tools',[]) if t['name']==name),None)
    if snapshot is None:raise SafeError('Tool has not been reviewed. Test and publish the service again.')
    check_account_arguments(service,arguments)
    try:
        async with asyncio.timeout(45):
            async with connection(service,config) as (session,values):
                # A package update cannot silently change an approved tool contract.
                current=await reviewed_tools(session,values)
                tool=next((t for t in current if t['name']==name),None)
                if not tool or tool_hash(tool)!=tool_hash(snapshot):
                    raise SafeError('Tool definition changed upstream. Review and publish again before calling it.')
                result=await session.call_tool(name,arguments)
                return types.CallToolResult.model_validate(scrub(result.model_dump(mode='json',exclude_none=True),values))
    except SafeError:raise
    except Exception:
        raise SafeError('MCP call failed. Check service access; upstream diagnostics were suppressed to protect credentials.') from None


async def reviewed_tools(session,values):
    tools=[]
    cursor=None
    for _ in range(10):
        page=await session.list_tools(cursor=cursor)
        tools.extend(scrub(t.model_dump(mode='json',exclude_none=True),values) for t in page.tools)
        if len(tools)>100:raise SafeError('Connector exposes too many tools; narrow its profile.')
        cursor=page.nextCursor
        if not cursor:break
    else:raise SafeError('Connector tool catalogue exceeded page limit.')
    if len({t['name'] for t in tools})!=len(tools):raise SafeError('Connector returned duplicate tool names.')
    for tool in tools:
        validate_schema(tool['inputSchema'])
        if tool.get('outputSchema') is not None:validate_schema(tool['outputSchema'])
    return tools


def check_account_arguments(service,value):
    if service.get('service')!='cloudflare':return
    if isinstance(value,dict):
        for key,item in value.items():
            if key.lower().replace('_','')=='accountid' and item!=service['account_id']:
                raise SafeError('Tool arguments conflict with this Cloudflare profile account. Select the correct profile explicitly.')
            check_account_arguments(service,item)
    elif isinstance(value,list):
        for item in value:check_account_arguments(service,item)
