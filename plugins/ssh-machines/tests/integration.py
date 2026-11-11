"""Real native plugin + Windows OpenSSH against an ephemeral synthetic SSH server."""
import argparse
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import paramiko

parser=argparse.ArgumentParser();parser.add_argument('--core',required=True);args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[3]
logging.getLogger('paramiko').setLevel(logging.CRITICAL)


def protect_private_key(path):
    import win32api,win32security,ntsecuritycon
    token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32security.TOKEN_QUERY)
    sid=win32security.GetTokenInformation(token,win32security.TokenUser)[0]
    acl=win32security.ACL();acl.AddAccessAllowedAce(win32security.ACL_REVISION,ntsecuritycon.FILE_ALL_ACCESS,sid)
    win32security.SetNamedSecurityInfo(str(path),win32security.SE_FILE_OBJECT,win32security.DACL_SECURITY_INFORMATION|win32security.PROTECTED_DACL_SECURITY_INFORMATION,None,None,acl,None)


class SSHFixture:
    def __init__(self,key,client):
        self.key=key;self.client=client;self.commands=[];self.stop=threading.Event();self.connections=[]
        self.socket=socket.socket();self.socket.bind(('127.0.0.1',0));self.port=self.socket.getsockname()[1]
        self.socket.listen();self.socket.settimeout(.2)
        self.thread=threading.Thread(target=self.accept,daemon=True);self.thread.start()
    def accept(self):
        while not self.stop.is_set():
            try:conn,_=self.socket.accept()
            except socket.timeout:continue
            except OSError:break
            t=threading.Thread(target=self.handle,args=(conn,),daemon=True);t.start();self.connections.append(t)
    def handle(self,conn):
        fixture=self
        class Server(paramiko.ServerInterface):
            def __init__(self):self.event=threading.Event();self.command=None
            def check_auth_publickey(self,username,key):return paramiko.AUTH_SUCCESSFUL if username=='fixture-user' and key==fixture.client else paramiko.AUTH_FAILED
            def get_allowed_auths(self,username):return 'publickey'
            def check_channel_request(self,kind,chanid):return paramiko.OPEN_SUCCEEDED if kind=='session' else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
            def check_channel_exec_request(self,channel,command):
                self.command=command.decode();fixture.commands.append(self.command);self.event.set()
                return self.command in ('uname -s; id -un', "systemctl restart -- 'nginx' && printf 'Service restart completed\\n'")
        transport=paramiko.Transport(conn);transport.add_server_key(self.key);server=Server()
        try:
            transport.start_server(server=server);channel=transport.accept(5)
            if channel and server.event.wait(5):
                channel.sendall(b'Linux\nfixture-user\n');channel.send_exit_status(0);channel.shutdown_write()
                deadline=time.monotonic()+2
                while transport.is_active() and time.monotonic()<deadline:time.sleep(.02)
                channel.close()
        except (EOFError,paramiko.SSHException,OSError):pass
        finally:transport.close();conn.close()
    def close(self):
        self.stop.set();self.socket.close();self.thread.join(3)
        for t in self.connections:t.join(7)


with tempfile.TemporaryDirectory(prefix='ecpa ssh fixture-') as folder:
    home=Path(folder);plugins=home/'plugins';plugins.mkdir()
    shutil.copy2(ROOT/'target/release/ssh_machines.dll',plugins/'ssh-machines.dll')
    key=paramiko.RSAKey.generate(2048);client=paramiko.RSAKey.generate(2048);client_path=home/'client-key'
    client.write_private_key_file(str(client_path));protect_private_key(client_path);public='ssh-rsa '+key.get_base64()
    fp='SHA256:'+base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
    fixture=SSHFixture(key,client)
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    cfg={'host':'127.0.0.1','port':port,'auth-dir':str(home/'auth'),'remote-management':{'secret-key':'fixture-core-key','allow-remote':False,'disable-control-panel':True},'api-keys':['fixture-client'],'plugins':{'enabled':True,'dir':str(plugins),'configs':{'ssh-machines':{'enabled':True,'data_dir':str(home/'data')}}}}
    config=home/'core.yaml';config.write_text(json.dumps(cfg));base=f'http://127.0.0.1:{port}'
    process=subprocess.Popen([str(Path(args.core).resolve()),'-config',str(config),'--local-model'],cwd=home,env={**os.environ,'LOCALAPPDATA':str(home/'local')},stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    def request(route,body=None,auth=True):
        req=urllib.request.Request(base+route,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**({'Authorization':'Bearer fixture-core-key'} if auth else {})})
        try:
            with urllib.request.urlopen(req,timeout=25) as response:return response.status,response.read()
        except urllib.error.HTTPError as error:return error.code,error.read()
    def call(action=None,**body):
        status,raw=request('/v0/management/ssh-machines/'+('action' if action else 'state'),{'action':action,**body} if action else None)
        assert status==200,(status,raw.decode());return json.loads(raw)
    try:
        for _ in range(100):
            try:
                if request('/v0/management/ssh-machines/state')[0]==200:break
            except OSError:pass
            time.sleep(.1)
        else:raise RuntimeError('Isolated core did not start')
        status,raw=request('/v0/management/plugins')
        assert status==200
        plugin=next(p for p in json.loads(raw)['plugins'] if p['id']=='ssh-machines')
        assert plugin['metadata']['name']=='SSH and Machines', 'Host must return a plain-text sidebar label'
        assert request('/v0/management/ssh-machines/state',auth=False)[0]==401
        status,page=request('/v0/resource/plugins/ssh-machines/editor',auth=False)
        assert status==200 and b'fixture-user' not in page
        scan=call('scan',host='127.0.0.1',user='fixture-user',port=fixture.port)
        assert any(row['fingerprint']==fp for row in scan['keys'])
        machine={'id':'fixture','name':'Fixture','host':'127.0.0.1','port':fixture.port,'user':'fixture-user','os':'linux','auth':'key-file','identity_file':str(client_path),'host_key':public,'labels':['test']}
        initial=call();version=initial['version']
        assert request('/v0/management/ssh-machines/action',{'action':'save','machine':machine,'version':version,'reviewed_fingerprint':'wrong'})[0]==400
        state=call('save',machine=machine,version=version,reviewed_fingerprint=fp)
        code,raw=request('/v0/management/ssh-machines/action',{'action':'test','id':'fixture'})
        assert code==200,(raw.decode(),fixture.commands)
        result=json.loads(raw);assert result['connected'] and 'fixture-user' in result['diagnostic']
        assert fixture.commands==['uname -s; id -un']
        # Reuse the exact saved machine through the gateway's single shared helper.
        from ecpa_gateway.app import Controller
        from ecpa_gateway.registry import atomic,encode
        from ecpa_gateway.security import token_digest,SafeError
        gateway_path=home/'gateway/gateway-runtime.json'
        atomic(gateway_path,encode({'host_id':'fixture-runtime','data_dir':str(gateway_path.parent),
            'helper_executable':str(ROOT/'target/release/ecpa-connect.exe'),'ssh_data_dir':str(home/'data'),
            'identities':{'fixture-client':{'sha256':token_digest('fixture-gateway-client'),'services':['machine-fixture']}}}))
        controller=Controller(gateway_path)
        async def gateway_scenario():
            definition={'id':'machine-fixture','name':'Machine fixture','kind':'ssh','machine_id':'fixture','execution_host':'fixture-runtime',
                'enabled':False,'credential_refs':[],'allowed_tools':[],
                'ssh_operations':{'restart-web':{'action':'restart-service','service':'nginx'}}}
            review=await controller.admin({'action':'test','service':definition})
            _,version=controller.registry.load()
            await controller.admin({'action':'publish','review':review['review'],'version':version,'allowed_tools':['diagnostics','request_operation','request_status'],'confirm_read_only':True})
            assert fixture.commands==['uname -s; id -un']*2
            requested=await controller.call('fixture-client','machine-fixture__request_operation',{'operation':'restart-web'})
            record=json.loads(requested.content[0].text)
            assert len(fixture.commands)==2,'Operation executed before approval'
            result=await controller.admin({'action':'approve-request','id':record['request_id'],'confirm':True})
            assert result['status']=='completed',result
            assert fixture.commands[-1]=="systemctl restart -- 'nginx' && printf 'Service restart completed\\n'"
            try:await controller.admin({'action':'approve-request','id':record['request_id'],'confirm':True})
            except SafeError:pass
            else:raise AssertionError('Approval was replayed')
            assert len(fixture.commands)==3
        __import__('asyncio').run(gateway_scenario())
        expected_commands=list(fixture.commands)
        terminal=call('terminal',id='fixture');assert 'StrictHostKeyChecking=yes' in terminal['command'] and 'ProxyCommand=none' in terminal['command']
        assert request('/v0/management/ssh-machines/action',{'action':'delete','id':'fixture','version':version})[0]==400
        wrong_client=paramiko.RSAKey.generate(2048);wrong_path=home/'wrong-client-key';wrong_client.write_private_key_file(str(wrong_path));protect_private_key(wrong_path)
        wrong_identity={**machine,'identity_file':str(wrong_path)}
        state=call('save',machine=wrong_identity,version=state['version'],reviewed_fingerprint=fp)
        assert request('/v0/management/ssh-machines/action',{'action':'test','id':'fixture'})[0]==400
        assert fixture.commands==expected_commands,'Wrong key fell back to a different account identity'
        changed=paramiko.RSAKey.generate(2048);bad={**machine,'host_key':'ssh-rsa '+changed.get_base64()}
        bad_fp='SHA256:'+base64.b64encode(hashlib.sha256(changed.asbytes()).digest()).decode().rstrip('=')
        state=call('save',machine=bad,version=state['version'],reviewed_fingerprint=bad_fp)
        assert request('/v0/management/ssh-machines/action',{'action':'test','id':'fixture'})[0]==400
        assert fixture.commands==expected_commands,'Wrong host key reached remote execution'
        export=json.dumps(call('export'));assert 'PRIVATE KEY' not in export
        assert request('/v0/management/ssh-machines/action',{'action':'run','command':'anything'})[0]==400
        call('delete',id='fixture',version=state['version']);assert not call()['machines']
        print('PASS: isolated native core + real OpenSSH handshake/diagnostics, pinned-key rejection, explicit identity, private route boundary, stale edits single-use gateway approval, and no arbitrary command API')
    finally:
        process.terminate();process.wait(timeout=10);fixture.close()
