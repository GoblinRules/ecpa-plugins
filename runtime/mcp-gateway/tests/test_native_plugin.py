"""Opt-in real core/DLL forwarding test, isolated from production services."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import httpx
import pytest
from ecpa_gateway.security import vault_put,auth_target
from ecpa_gateway.registry import atomic,encode
from test_gateway import config,live


@pytest.mark.skipif(os.name!='nt' or not os.environ.get('ECPA_TEST_CORE'),reason='Set ECPA_TEST_CORE to test isolated native integration')
def test_native_management_bridge(live):
    import win32cred
    root=live.config_path.parent;cfg=live.config()
    target=auth_target(root,'admin');vault_put(target,'fixture-admin')
    cfg['identities']['admin']['vault_target']=target;atomic(live.config_path,encode(cfg))
    plugin_dir=root/'plugins';plugin_dir.mkdir()
    dll=Path(__file__).resolve().parents[3]/'target/release/connections_manager.dll'
    shutil.copy2(dll,plugin_dir/'connections-manager.dll')
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    core_cfg={'host':'127.0.0.1','port':port,'auth-dir':str(root/'core-auth'),
        'remote-management':{'secret-key':'fixture-core-admin','allow-remote':False,'disable-control-panel':True},
        'api-keys':['fixture-api-key'],'plugins':{'enabled':True,'dir':str(plugin_dir),'configs':{'connections-manager':{'enabled':True,'data_dir':str(root)}}}}
    path=root/'core.yaml';path.write_text(json.dumps(core_cfg))
    process=None
    try:
        process=subprocess.Popen([os.environ['ECPA_TEST_CORE'],'-config',str(path),'--local-model'],cwd=root,
            env={**os.environ,'LOCALAPPDATA':str(root/'local')},stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        base=f'http://127.0.0.1:{port}'
        with httpx.Client(base_url=base,trust_env=False,timeout=10) as client:
            for _ in range(100):
                try:
                    ready=client.get('/v0/management/connections-manager/state',headers={'Authorization':'Bearer fixture-core-admin'})
                    if ready.status_code==200:break
                except httpx.TransportError:pass
                time.sleep(.1)
            else:pytest.fail('Isolated core did not start')
            route='/v0/management/connections-manager/gateway'
            assert client.post(route,json={'action':'state'}).status_code==401
            response=client.post(route,json={'action':'state'},headers={'Authorization':'Bearer fixture-core-admin'})
            assert response.status_code==200
            assert response.json()['runtime']['host_id']=='test-runtime'
            page=client.get('/v0/resource/plugins/connections-manager/gateway')
            assert page.status_code==200 and 'MCP services' in page.text
            assert 'fixture-admin' not in page.text and 'fixture-admin' not in response.text
    finally:
        if process is not None:process.terminate();process.wait(timeout=10)
        win32cred.CredDelete(target,1,0)
