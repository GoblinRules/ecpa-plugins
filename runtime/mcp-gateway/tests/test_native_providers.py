"""Real core/DLL routing to a synthetic upstream; no provider inference is sent."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import httpx
import pytest
from ecpa_gateway.registry import atomic, encode
from ecpa_gateway.security import auth_target, vault_put
from test_gateway import config, live
from test_service_integrations import upstream, profile


@pytest.mark.skipif(os.name!='nt' or not os.environ.get('ECPA_TEST_CORE'),reason='Requires isolated native core')
async def test_real_core_model_routes_streaming_and_disable(live,upstream):
    import win32cred
    root=live.config_path.parent;cfg=live.config();target=auth_target(root,'admin')
    vault_put(target,'fixture-admin');cfg['identities']['admin']['vault_target']=target;atomic(live.config_path,encode(cfg))
    review=await live.admin({'action':'test','service':profile('provider')})
    _,version=live.registry.load()
    await live.admin({'action':'publish','review':review['review'],'version':version,'confirm_core_access':True})
    plugins=root/'plugins';plugins.mkdir()
    shutil.copy2(Path(__file__).resolve().parents[3]/'target/release/connections_manager.dll',plugins/'connections-manager.dll')
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    core_cfg={'host':'127.0.0.1','port':port,'auth-dir':str(root/'auth'),
        'remote-management':{'secret-key':'fixture-core-admin','allow-remote':False,'disable-control-panel':True},
        'api-keys':['fixture-frontend-client'],'request-retry':0,
        'plugins':{'enabled':True,'dir':str(plugins),'configs':{'connections-manager':{'enabled':True,'data_dir':str(root)}}}}
    path=root/'core.yaml';path.write_text(json.dumps(core_cfg),encoding='utf-8');process=None
    try:
        process=subprocess.Popen([os.environ['ECPA_TEST_CORE'],'-config',str(path),'--local-model'],cwd=root,
            env={**os.environ,'LOCALAPPDATA':str(root/'local')},stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=45) as client:
            headers={'Authorization':'Bearer fixture-frontend-client'}
            for _ in range(100):
                try:
                    models=await client.get('/v1/models',headers=headers)
                    if models.status_code==200 and 'ecpa-work--primary' in models.text:break
                except httpx.TransportError:pass
                await __import__('asyncio').sleep(.1)
            else:pytest.fail('Managed model was not registered by the isolated core')
            payload={'model':'ecpa-work--primary','messages':[{'role':'user','content':'synthetic fixture'}]}
            assert (await client.post('/v1/chat/completions',json=payload)).status_code==401
            reply=await client.post('/v1/chat/completions',json=payload,headers=headers)
            assert reply.status_code==200,reply.text
            assert reply.json()['choices'][0]['message']['content']=='fixture reply'
            reply=await client.post('/v1/chat/completions',json={**payload,'stream':True},headers=headers)
            assert reply.status_code==200 and 'fixture reply' in reply.text and '[DONE]' in reply.text,reply.text
            # The host translates a Codex Responses request into the declared OpenAI format.
            reply=await client.post('/v1/responses',json={'model':'ecpa-work--primary','input':'fixture','stream':False},headers=headers)
            assert reply.status_code==200 and 'fixture reply' in reply.text,reply.text
            _,version=live.registry.load();await live.admin({'action':'disable','id':'work','version':version})
            calls=len(upstream[0])
            reply=await client.post('/v1/chat/completions',json=payload,headers=headers)
            assert reply.status_code>=400 and len(upstream[0])==calls
        assert 'fixture-service-value' not in path.read_text() and 'fixture-service-value' not in live.registry.path.read_text()
    finally:
        if process is not None:process.terminate();process.wait(timeout=10)
        win32cred.CredDelete(target,1,0)
