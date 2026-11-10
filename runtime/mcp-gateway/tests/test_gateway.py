import asyncio
import copy
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time

import httpx
import pytest
import uvicorn
from mcp import ClientSession, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp.client.stdio import stdio_client

from ecpa_gateway.app import create_app, Controller
from ecpa_gateway import clients
from ecpa_gateway.registry import Registry, encode, atomic, validate_service
from ecpa_gateway.security import SafeError, token_digest, clean_env


@pytest.fixture
def config(tmp_path):
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    identities={}
    for identity,services in [('admin',[]),('codex',['*']),('claude',['sample-two']),('denied',[])]:
        secret=tmp_path/(identity+'.secret');secret.write_text('fixture-'+identity)
        identities[identity]={'secret_file':str(secret),'sha256':token_digest('fixture-'+identity),'services':services}
    data={'schema_version':1,'host_id':'test-runtime','data_dir':str(tmp_path),'url':f'http://127.0.0.1:{port}/mcp',
        'helper_executable':str(Path(__file__).resolve().parents[3]/'target/debug/ecpa-connect.exe'),
        'bws_executable':str(tmp_path/'bws.exe'),'identities':identities,
        'client_paths':{'codex':str(tmp_path/'config.toml'),'claude':str(tmp_path/'claude.json'),'native':str(tmp_path/'mcp-servers.json')}}
    path=tmp_path/'gateway-runtime.json';atomic(path,encode(data));return path


def service(id='sample-one'):
    return {'id':id,'name':id,'kind':'sample','enabled':False,'credential_refs':[],'allowed_tools':[], 'execution_host':'test-runtime'}


async def publish(controller,s,tools=('status','echo')):
    review=await controller.admin({'action':'test','service':s})
    _,version=controller.registry.load()
    return await controller.admin({'action':'publish','review':review['review'],'version':version,
                                  'allowed_tools':list(tools),'confirm_read_only':True})


@pytest.fixture
def live(config):
    app=create_app(config)
    port=int(app.controller.config()['url'].split(':')[-1].split('/')[0])
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='critical',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    else:raise RuntimeError('test gateway did not start')
    yield app.controller
    server.should_exit=True;thread.join(10)
    assert not thread.is_alive()


async def mcp_call(config,identity,method='tools/list',name=None,args=None):
    async with httpx.AsyncClient(headers={'Authorization':'Bearer fixture-'+identity},follow_redirects=False,trust_env=False) as client:
        async with streamable_http_client(config['url'],http_client=client) as streams:
            async with ClientSession(streams[0],streams[1]) as session:
                await session.initialize()
                if method=='tools/list':return await session.list_tools()
                return await session.call_tool(name,args or {})


async def test_handshake_policy_concurrency_and_revocation(live):
    await publish(live,service())
    await publish(live,service('sample-two'))
    cfg=live.config()
    a,b=await asyncio.gather(mcp_call(cfg,'codex'),mcp_call(cfg,'claude'))
    assert len(a.tools)==4 and {t.name for t in b.tools}=={'sample-two__status','sample-two__echo'}
    replies=await asyncio.gather(mcp_call(cfg,'codex','call','sample-one__echo',{'value':'client-a'}),mcp_call(cfg,'claude','call','sample-two__echo',{'value':'client-b'}))
    assert not any(r.isError for r in replies)
    assert 'client-a' in replies[0].content[0].text and 'client-b' not in replies[0].content[0].text
    assert 'client-b' in replies[1].content[0].text
    denied=await mcp_call(cfg,'claude','call','sample-one__status')
    assert denied.isError
    assert (await mcp_call(cfg,'codex','call','sample-one__delete')).isError
    assert (await mcp_call(cfg,'codex','call','sample-one__echo',{'wrong':'x'})).isError
    cfg['identities']['codex']['sha256']=token_digest('rotated')
    atomic(live.config_path,encode(cfg))
    async with httpx.AsyncClient(trust_env=False) as client:
        r=await client.post(cfg['url'],headers={'Authorization':'Bearer fixture-codex'},json={})
        assert r.status_code==401


async def test_http_auth_origin_and_management_separation(live):
    cfg=live.config();base=cfg['url'].removesuffix('/mcp')
    async with httpx.AsyncClient(trust_env=False) as client:
        assert (await client.post(cfg['url'],json={})).status_code==401
        assert (await client.post(cfg['url'],headers={'Authorization':'Bearer fixture-admin'},json={})).status_code==401
        assert (await client.post(base+'/admin',headers={'Authorization':'Bearer fixture-codex'},json={'action':'state'})).status_code==401
        assert (await client.post(cfg['url'],headers={'Authorization':'Bearer fixture-codex','Origin':'https://evil.example'},json={})).status_code==403
        assert (await client.post(base+'/admin',headers={'Authorization':'Bearer fixture-admin'},content=b'x'*65537)).status_code==413


async def test_registry_review_conflict_restart_and_rollback(config):
    c=Controller(config)
    s=service();review=await c.admin({'action':'test','service':s})
    with pytest.raises(SafeError):await c.admin({'action':'publish','review':review['review'],'version':c.registry.load()[1],'allowed_tools':['status'],'confirm_read_only':False})
    await publish(c,s,('status',))
    d,v=c.registry.load();d['extension']={'preserve':True};c.registry.commit(d,v)
    with pytest.raises(SafeError):c.registry.remove(s['id'],v)
    before=c.registry.load()[0]
    await c.admin({'action':'disable','id':s['id'],'version':c.registry.load()[1]})
    assert Controller(config).registry.load()[0]['extension']=={'preserve':True}
    c.registry.restore(c.registry.backups()[0],c.registry.load()[1])
    assert c.registry.load()[0]==before
    assert c.tools('codex')[0].name=='sample-one__status'


def test_client_preservation_conflict_and_rollback(config):
    cfg=json.loads(config.read_bytes());paths=cfg['client_paths']
    Path(paths['codex']).write_text('# keep comment\nmodel = "fixture"\n[mcp_servers.portainer]\ncommand="old-launcher"\n[mcp_servers.unrelated]\ncommand="keep"\ncustom=true\n')
    Path(paths['claude']).write_text('{"unknown":{"keep":true},"mcpServers":{"unrelated":{"command":"keep","future":42}}}')
    Path(paths['native']).write_text('[{"id":"existing","unknown":{"preserve":true}}]')
    originals={k:Path(p).read_bytes() for k,p in paths.items()}
    plans=clients.preview(config,cfg,list(paths),{'codex':['portainer']})
    tx=clients.apply(config.parent,plans)
    assert 'keep comment' in Path(paths['codex']).read_text() and '[mcp_servers.portainer]' not in Path(paths['codex']).read_text()
    assert json.loads(Path(paths['claude']).read_bytes())['unknown']['keep']
    assert json.loads(Path(paths['native']).read_bytes())[0]['unknown']['preserve']
    clients.rollback(config.parent,tx)
    assert all(Path(paths[k]).read_bytes()==v for k,v in originals.items())
    plans=clients.preview(config,cfg,['codex'])
    Path(paths['codex']).write_text('# external edit\n')
    with pytest.raises(SafeError):clients.apply(config.parent,plans)
    assert Path(paths['codex']).read_text()=='# external edit\n'


def test_reference_only_import_and_secret_environment(config,monkeypatch):
    monkeypatch.setenv('BWS_ACCESS_TOKEN','fixture-machine-token')
    monkeypatch.setenv('GITHUB_TOKEN','fixture-other-token')
    assert 'BWS_ACCESS_TOKEN' not in clean_env() and 'GITHUB_TOKEN' not in clean_env()
    cfg=json.loads(config.read_bytes())
    Path(cfg['client_paths']['claude']).write_text(json.dumps({'mcpServers':{'private':{'command':'x','env':{'SECRET':'fixture'}}}}))
    result=clients.inventory(cfg)
    assert 'fixture' not in json.dumps(result)
    with pytest.raises(SafeError):clients.import_candidate(cfg,'claude','private')
    s=service();s['api_key']='fixture-secret'
    with pytest.raises(SafeError):validate_service(s)


async def test_bridge_real_stdio(live):
    await publish(live,service(),('status',))
    params=StdioServerParameters(command=sys.executable,args=['-m','ecpa_gateway.cli','--config',str(live.config_path),'bridge','--identity','codex'],env=clean_env())
    with open(os.devnull,'w') as err:
        async with stdio_client(params,errlog=err) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                assert [t.name for t in (await session.list_tools()).tools]==['sample-one__status']
                result=await session.call_tool('sample-one__status',{})
                assert not result.isError and 'synthetic' in result.content[0].text
