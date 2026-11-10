"""Optional standards-based remote MCP OAuth, using the SDK's PKCE/refresh flow.

Interactive consent is a separate CLI operation on the runtime host. Background
tool calls never open a browser. Tokens are profile/resource scoped and protected
with Windows DPAPI (Linux uses an owner-only file pending OS secret-store setup).
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit, parse_qs
import webbrowser
from contextlib import asynccontextmanager
import portalocker
import httpx
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientMetadata, OAuthClientInformationFull, OAuthToken
from .registry import atomic, encode
from .security import SafeError, validate_url


class OAuthStorage:
    def __init__(self,service,config,values=None):
        key=hashlib.sha256((service['id']+'\0'+service['url']).encode()).hexdigest()
        self.path=Path(config['data_dir'])/'oauth'/key
        self.values=values if values is not None else []
    def track(self,data):
        for section in ('tokens','client'):
            for key in ('access_token','refresh_token','client_secret'):
                value=data.get(section,{}).get(key)
                if value and value not in self.values:self.values.append(value)
    def load(self):
        if not self.path.exists():return {}
        raw=self.path.read_bytes()
        if os.name=='nt':
            import win32crypt
            raw=win32crypt.CryptUnprotectData(raw,None,None,None,0)[1]
        data=json.loads(raw);self.track(data);return data
    def save(self,value):
        self.track(value)
        raw=encode(value)
        if os.name=='nt':
            import win32crypt
            raw=win32crypt.CryptProtectData(raw,'ECPA MCP OAuth',None,None,None,0)
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        atomic(self.path,raw)
        if os.name!='nt':self.path.chmod(0o600)
    async def get_tokens(self):
        data=self.load()
        if not data.get('tokens'):return None
        tokens=data['tokens']
        if data.get('expires_at'):tokens['expires_in']=max(0,int(data['expires_at']-time.time()))
        return OAuthToken.model_validate(tokens)
    async def set_tokens(self,tokens):
        data=self.load();data['tokens']=tokens.model_dump(mode='json',exclude_none=True)
        data['expires_at']=time.time()+tokens.expires_in if tokens.expires_in else None
        self.save(data)
    async def get_client_info(self):
        data=self.load()
        return OAuthClientInformationFull.model_validate(data['client']) if data.get('client') else None
    async def set_client_info(self,client_info):
        data=self.load();data['client']=client_info.model_dump(mode='json',exclude_none=True);self.save(data)


def origin(url):
    u=urlsplit(url);return u.scheme+'://'+u.netloc


def provider(service,config,redirect_handler=None,callback_handler=None,values=None):
    async def no_interaction(*_):raise SafeError('This OAuth profile needs interactive authorization on the runtime host. Run oauth-login for this profile.')
    settings=service['oauth']
    return OAuthClientProvider(service['url'],OAuthClientMetadata(
        client_name='ECPA managed MCP',redirect_uris=[f"http://127.0.0.1:{settings.get('callback_port',8770)}/callback"],
        token_endpoint_auth_method='none',scope=settings.get('scope')),
        storage=OAuthStorage(service,config,values),redirect_handler=redirect_handler or no_interaction,
        callback_handler=callback_handler or no_interaction)


def request_guard(service):
    allowed={origin(service['url']),*service['oauth']['allowed_origins']}
    async def check(request):
        if origin(str(request.url)) not in allowed:
            raise SafeError('OAuth advertised an unapproved destination. Review its official authorization origin before allowing it.')
    return check


@asynccontextmanager
async def profile_lock(service,config):
    path=OAuthStorage(service,config).path
    path.parent.mkdir(parents=True,exist_ok=True)
    with Path(str(path)+'.lock').open('a+b') as handle:
        acquired=False
        try:
            async with asyncio.timeout(10):
                while not acquired:
                    try:
                        portalocker.lock(handle,portalocker.LOCK_EX|portalocker.LOCK_NB)
                        acquired=True
                    except portalocker.exceptions.LockException:await asyncio.sleep(.1)
            yield
        except TimeoutError:
            raise SafeError('OAuth profile is busy authorizing or refreshing; retry after it completes.') from None
        finally:
            if acquired:portalocker.unlock(handle)


async def login(service,config):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    if service.get('kind')!='http' or not service.get('oauth'):raise SafeError('Select a hosted MCP profile configured for OAuth.')
    port=service['oauth'].get('callback_port',8770)
    future=asyncio.get_running_loop().create_future()
    async def handle(reader,writer):
        try:
            line=await asyncio.wait_for(reader.readline(),5)
            if len(line)>8192:raise ValueError()
            target=line.decode().split(' ')[1]
            query=parse_qs(urlsplit(target).query)
            if urlsplit(target).path!='/callback' or not query.get('code') or not query.get('state'):raise ValueError()
            if not future.done():future.set_result((query['code'][0],query['state'][0]))
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nAuthorization returned. Check the ECPA runtime terminal for the result.')
        except Exception:
            writer.write(b'HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\nInvalid callback.')
        finally:
            await writer.drain();writer.close()
    async def redirect(url):
        if origin(url) not in service['oauth']['allowed_origins']:raise SafeError('Authorization page origin was not approved.')
        # Consent is explicit: this entry point is invoked by the operator, never a tool call.
        webbrowser.open(url)
        print('Complete sign-in in the browser on this runtime host. Waiting up to five minutes.',file=__import__('sys').stderr)
    async def callback():return await asyncio.wait_for(future,300)
    server=await asyncio.start_server(handle,'127.0.0.1',port,limit=8192)
    async with server, profile_lock(service,config):
        auth=provider(service,config,redirect,callback)
        async with httpx.AsyncClient(auth=auth,timeout=30,follow_redirects=False,trust_env=False,event_hooks={'request':[request_guard(service)]}) as client:
            async with streamable_http_client(service['url'],http_client=client) as streams:
                async with ClientSession(streams[0],streams[1]) as session:
                    await session.initialize()
                    await session.list_tools()
    return {'authorized':service['id'],'host':config['host_id'],'message':'OAuth stored for this profile/resource and runtime identity. Test and publish its tools next.'}
