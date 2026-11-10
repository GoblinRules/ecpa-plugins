import asyncio
import copy
import json
import os
from pathlib import Path
import sys
import subprocess
import socket
from urllib.parse import urlsplit
from types import SimpleNamespace

import httpx
import pytest
from mcp import types
from mcp.shared.auth import OAuthToken, OAuthClientInformationFull

from ecpa_gateway import connectors, security, oauth, jobs
from ecpa_gateway.app import Controller
from ecpa_gateway.identities import grant_client,revoke_client
from ecpa_gateway.registry import atomic,encode,validate_service,validate_schema
from ecpa_gateway.security import SafeError,token_digest
from test_gateway import config, service, publish, mcp_call


@pytest.mark.skipif(os.name!='nt',reason='Windows consoleless background worker')
async def test_consoleless_worker(config):
    cfg=json.loads(config.read_bytes())
    executable=Path(sys.executable).with_name('pythonw.exe')
    process=subprocess.Popen([str(executable),'-m','ecpa_gateway.cli','--config',str(config),'serve'],
        env=security.clean_env(),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        for _ in range(100):
            assert process.poll() is None,'Consoleless worker exited during startup'
            try:
                with socket.create_connection(('127.0.0.1',urlsplit(cfg['url']).port),timeout=.1):pass
                break
            except OSError:await asyncio.sleep(.1)
        else:pytest.fail('Consoleless worker did not listen')
        assert (await mcp_call(cfg,'codex')).tools==[]
    finally:
        if process.poll() is None:
            subprocess.run([str(Path(os.environ['SYSTEMROOT'])/'System32/taskkill.exe'),'/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        process.wait(timeout=10)


@pytest.mark.skipif(os.name!='nt',reason='Windows credential interoperability')
def test_windows_bootstrap_and_raw_utf8_vault(tmp_path):
    import win32cred
    from ecpa_gateway.cli import bootstrap
    path=tmp_path/'gateway-runtime.json'
    try:
        bootstrap(path,sys.executable,sys.executable)
        cfg=json.loads(path.read_bytes())
        for identity in ('admin','codex','claude'):
            value=security.auth_secret(cfg,identity)
            assert token_digest(value)==cfg['identities'][identity]['sha256']
        target=security.auth_target(tmp_path,'fixture')
        security.vault_put(target,'synthetic-UTF8-é')
        assert security.vault_get(target)=='synthetic-UTF8-é'
        # Raw bytes are the same convention as Rust's String::from_utf8 reader.
        from ecpa_gateway.winvault import api,Credential
        import ctypes
        dll=api();record=ctypes.POINTER(Credential)()
        assert dll.CredReadW(target,1,0,ctypes.byref(record))
        try:assert ctypes.string_at(record.contents.CredentialBlob,record.contents.CredentialBlobSize)=='synthetic-UTF8-é'.encode()
        finally:dll.CredFree(record)
    finally:
        for name in ('admin','codex','claude','fixture'):
            try:win32cred.CredDelete(security.auth_target(tmp_path,name),1,0)
            except Exception:pass


async def test_bws_rotation_and_scoped_environment(config,monkeypatch):
    cfg=json.loads(config.read_bytes());cfg['bws_executable']=sys.executable
    monkeypatch.setenv('BWS_ACCESS_TOKEN','machine-fixture')
    monkeypatch.setenv('OTHER_SECRET','not-for-bws')
    ref={'provider':'bitwarden','region':'eu','secret_id':'11111111-1111-1111-1111-111111111111'}
    current=['service-one'];seen=[]
    async def fake(command,env,timeout=30):
        seen.append((command,env))
        return json.dumps({'id':ref['secret_id'],'value':current[0]}).encode()
    monkeypatch.setattr(security,'bounded_process',fake)
    assert await security.resolve(ref,cfg)=='service-one'
    current[0]='service-rotated'
    assert await security.resolve(ref,cfg)=='service-rotated'
    assert len(seen)==2
    for cmd,env in seen:
        assert 'machine-fixture' not in cmd and env['BWS_ACCESS_TOKEN']=='machine-fixture'
        assert 'OTHER_SECRET' not in env and 'https://vault.bitwarden.eu' in cmd
    cfg['bws_executable']=str(config.parent/'missing.exe')
    with pytest.raises(SafeError,match='missing'):await security.resolve(ref,cfg)


async def test_credential_helper_failure_is_redacted():
    with pytest.raises(SafeError,match='denied') as error:
        await security.bounded_process([sys.executable,'-c','import sys; print("fixture-secret",file=sys.stderr); sys.exit(2)'],security.clean_env())
    assert 'fixture-secret' not in str(error.value)
    with pytest.raises(SafeError,match='timed out'):
        await security.bounded_process([sys.executable,'-c','import time; time.sleep(10)'],security.clean_env(),timeout=.2)


async def test_two_cloudflare_profiles_are_isolated(config,monkeypatch):
    cfg=json.loads(config.read_bytes())
    script=config.parent/'connector.py'
    script.write_text('''import os
from mcp.server.fastmcp import FastMCP
m=FastMCP("account-fixture")
@m.tool()
def status() -> dict:
    return {"account":os.environ.get("CLOUDFLARE_ACCOUNT_ID"),"key":os.environ.get("CLOUDFLARE_API_TOKEN"),"machine_leaked":"BWS_ACCESS_TOKEN" in os.environ,"other_leaked":"GITHUB_TOKEN" in os.environ}
if __name__=="__main__":m.run()
''')
    monkeypatch.setenv('BWS_ACCESS_TOKEN','never-child')
    monkeypatch.setenv('GITHUB_TOKEN','never-child-either')
    async def fake(ref,_):return 'synthetic-key-'+ref['target'].split('/')[-1]
    monkeypatch.setattr(connectors,'resolve',fake)
    async def run(n):
        s=service('cloudflare-'+n);s.update(kind='stdio',service='cloudflare',account_id=n*32,
            transport={'command':sys.executable,'args':[str(script)],'package':'synthetic-test','version':'1'},
            credential_refs=[{'kind':'env','name':'CLOUDFLARE_API_TOKEN','reference':{'provider':'windows-vault','target':'ECPA/'+n}}])
        s['tools']=await connectors.discover(s,cfg);s.update(enabled=True,reviewed_read_only=True,allowed_tools=['status'])
        result=await connectors.invoke(s,cfg,'status',{})
        raw=json.dumps(result.model_dump())
        assert 'synthetic-key' not in raw and 'never-child' not in raw
        payload=json.loads(result.content[0].text)
        assert payload['account']==n*32 and payload['key']=='[REDACTED]'
        assert not payload['machine_leaked'] and not payload['other_leaked']
    await asyncio.gather(run('a'),run('b'))
    profile={'service':'cloudflare','account_id':'a'*32}
    connectors.check_account_arguments(profile,{'account_id':'a'*32})
    with pytest.raises(SafeError,match='conflict'):
        connectors.check_account_arguments(profile,{'nested':[{'accountId':'b'*32}]})


async def test_wrangler_concurrent_profiles_and_config_conflicts(config,monkeypatch):
    cfg=json.loads(config.read_bytes());root=config.parent/'workspace';root.mkdir()
    (root/'wrangler.jsonc').write_text('{"name":"fixture","account_id":""}')
    fake_cli=config.parent/'fake_wrangler.py'
    fake_cli.write_text('''import os,json,time
time.sleep(.2)
print(json.dumps({k:os.environ.get(k) for k in ["CLOUDFLARE_ACCOUNT_ID","CLOUDFLARE_API_TOKEN","CF_API_KEY","CLOUDFLARE_API_KEY","BWS_ACCESS_TOKEN","HOME"]}))
''')
    cfg['workspaces']={'fixture':str(root)}
    monkeypatch.setenv('CLOUDFLARE_API_KEY','wrong-global-key')
    monkeypatch.setenv('CF_API_KEY','wrong-legacy-key')
    async def fake(ref,_):return 'fixture-'+ref['target'].split('/')[-1]
    monkeypatch.setattr(jobs,'resolve',fake)
    profiles=[]
    for n in ('a','b'):
        s=service('cloudflare-'+n);s.update(enabled=True,account_id=n*32,
            credential_refs=[{'kind':'env','name':'CLOUDFLARE_API_TOKEN','reference':{'provider':'windows-vault','target':'ECPA/'+n}}],
            wrangler={'node_executable':sys.executable,'entrypoint':str(fake_cli),'workspace_ids':['fixture'],'operations':{'verify':['whoami']}})
        profiles.append(s)
    replies=await asyncio.gather(*(jobs.run_wrangler(s,cfg,'fixture','verify') for s in profiles))
    values=[json.loads(r['output']) for r in replies]
    assert values[0]['HOME']!=values[1]['HOME']
    for n,value in zip(('a','b'),values):
        assert value['CLOUDFLARE_ACCOUNT_ID']==n*32 and value['CLOUDFLARE_API_TOKEN']=='[REDACTED]'
        assert value['CF_API_KEY'] is None and value['CLOUDFLARE_API_KEY'] is None and value['BWS_ACCESS_TOKEN'] is None
        assert not Path(value['HOME']).exists()
    (root/'wrangler.jsonc').write_text('{"account_id":"'+('b'*32)+'"}')
    with pytest.raises(SafeError,match='different Cloudflare account'):await jobs.run_wrangler(profiles[0],cfg,'fixture','verify')
    (root/'wrangler.jsonc').write_text('{}')
    (root/'.env').write_text('CLOUDFLARE_API_TOKEN=wrong')
    with pytest.raises(SafeError,match='overrides'):await jobs.run_wrangler(profiles[0],cfg,'fixture','verify')
    (root/'.env').unlink()
    nested=root/'nested';nested.mkdir();(nested/'wrangler.jsonc').write_text('{}')
    (nested/'.env').write_text('cloudflare_api_token=wrong-lowercase')
    profiles[0]['wrangler']['config_file']='nested/wrangler.jsonc'
    with pytest.raises(SafeError,match='overrides'):await jobs.run_wrangler(profiles[0],cfg,'fixture','verify')


async def test_oauth_storage_is_resource_scoped_encrypted_and_redacted(config):
    cfg=json.loads(config.read_bytes());s={'id':'oauth-one','url':'https://service.example/mcp','oauth':{'allowed_origins':['https://auth.example']}}
    values=[];store=oauth.OAuthStorage(s,cfg,values)
    await store.set_tokens(OAuthToken(access_token='access-fixture',refresh_token='refresh-fixture',token_type='Bearer',expires_in=600))
    await store.set_client_info(OAuthClientInformationFull(client_id='client-fixture',client_secret='client-secret-fixture',redirect_uris=['http://127.0.0.1:8770/callback']))
    assert (await store.get_tokens()).access_token=='access-fixture'
    assert set(values)=={'access-fixture','refresh-fixture','client-secret-fixture'}
    if os.name=='nt':assert b'access-fixture' not in store.path.read_bytes()
    assert await oauth.OAuthStorage({**s,'id':'oauth-two'},cfg).get_tokens() is None
    assert await oauth.OAuthStorage({**s,'url':'https://other.example/mcp'},cfg).get_tokens() is None
    assert connectors.scrub({'value':'refresh-fixture'},values)=={'value':'[REDACTED]'}
    guard=oauth.request_guard(s)
    await guard(httpx.Request('POST','https://auth.example/token'))
    with pytest.raises(SafeError,match='unapproved'):await guard(httpx.Request('POST','https://attacker.example/token'))
    assert oauth.provider(s,cfg) is not None


async def test_pagination_checks_all_reviewed_tools():
    tool=types.Tool(name='page_two',inputSchema={'type':'object'})
    class Session:
        async def list_tools(self,cursor=None):
            return types.ListToolsResult(tools=[] if cursor is None else [tool],nextCursor='second' if cursor is None else None)
    assert (await connectors.reviewed_tools(Session(),[]))[0]['name']=='page_two'
    validate_schema({'type':'object','$defs':{'value':{'type':'string'}},'properties':{'value':{'$ref':'#/$defs/value'}}})
    with pytest.raises(SafeError,match='external schema'):
        validate_schema({'$ref':'https://unapproved.example/schema'})


async def test_audit_unknown_names_and_explicit_project_grants(config):
    c=Controller(config);s=service();s.update(access_group='work',project_ids=['project-one'])
    await publish(c,s,('status',))
    assert not c.tools('codex')
    grant_client(config,'laptop-one',token_digest('laptop-secret'),[s['id']],['work'],['project-one'])
    assert len(c.tools('laptop-one'))==1
    await c.call('laptop-one','secret-in-unknown-tool__secret-value',{})
    audit=(await c.admin({'action':'activity'}))['activity']
    assert audit[-1]['tool']=='[unknown]' and 'secret-value' not in json.dumps(audit)
    revoke_client(config,'laptop-one');assert not c.tools('laptop-one')
