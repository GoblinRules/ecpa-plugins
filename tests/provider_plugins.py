"""Isolated real-core checks. Fixture builds never contact real providers."""
import argparse,json,os,shutil,socket,subprocess,sys,tempfile,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from go_build import go_environment
p=argparse.ArgumentParser();p.add_argument('--core',required=True);p.add_argument('--release',action='store_true');p.add_argument('--browser',action='store_true');args=p.parse_args()
ids=['claude-remote-login','zai-provider'];key='provider-isolated-fixture-management-key'
binaries=ROOT/'target'/('go' if args.release else 'go-fixture')
if not args.release:
 binaries.mkdir(parents=True,exist_ok=True);go,env=go_environment()
 for id in ids:
  subprocess.run([go,'build','-mod=vendor' if id=='zai-provider' else '-mod=readonly','-trimpath','-tags=integration_fixture','-buildmode=c-shared','-o',str(binaries/(id+'.dll')),'.'],cwd=ROOT/'plugins'/id,env=env,check=True)
with tempfile.TemporaryDirectory(prefix='ecpa-provider-fixture-') as tmp:
 root=Path(tmp);plugins=root/'plugins';plugins.mkdir();auth=root/'auth';auth.mkdir()
 for id in ids:shutil.copy2(binaries/(id+'.dll'),plugins/(id+'.dll'))
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 config={'host':'127.0.0.1','port':port,'auth-dir':str(auth),'remote-management':{'secret-key':key,'allow-remote':False,'disable-control-panel':True},'api-keys':['fixture-proxy-key'],'plugins':{'enabled':True,'dir':str(plugins),'configs':{id:{'enabled':True} for id in ids}}}
 (root/'config.yaml').write_text(json.dumps(config));base=f'http://127.0.0.1:{port}'
 def request(path,body=None,authorized=True):
  req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={**({'Authorization':'Bearer '+key} if authorized else {}),'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(req,timeout=15) as r:return r.status,r.read()
  except urllib.error.HTTPError as e:return e.code,e.read()
 def api(id,action,body):
  status,raw=request('/v0/management/plugins/'+id+'/'+action,body);assert status==200,(id,action,status,raw.decode());return json.loads(raw)
 with (root/'core.log').open('wb') as log:
  proc=subprocess.Popen([str(Path(args.core).resolve()),'-config',str(root/'config.yaml'),'--local-model'],cwd=root,env={**os.environ,'LOCALAPPDATA':str(root/'localappdata')},stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
  try:
   for _ in range(150):
    try:
     if request('/v0/resource/plugins/zai-provider/setup',authorized=False)[0]==200:break
    except OSError:pass
    if proc.poll() is not None:raise RuntimeError((root/'core.log').read_text(errors='replace'))
    time.sleep(.1)
   else:raise RuntimeError('Plugin startup failed: '+(root/'core.log').read_text(errors='replace')[:7000])
   for id,path in [('claude-remote-login','login'),('zai-provider','setup')]:
    status,html=request('/v0/resource/plugins/'+id+'/'+path,authorized=False);assert status==200 and b'<script>' in html
   for id,actions in [('claude-remote-login',['start','complete','confirm','cancel']),('zai-provider',['key/preview','key/confirm','key/cancel'])]:
    for action in actions:
     status,body=request('/v0/management/plugins/'+id+'/'+action,{},False)
     assert status in (401,403),(id,action,status,body)
     # Reset the core's failed-login counter with a valid read between probes.
     assert request('/v0/management/auth-files')[0]==200
   flow=api('claude-remote-login','start',{});assert flow['url'].startswith('https://claude.com/') and 'code_challenge=' in flow['url']
   assert request('/v0/management/plugins/claude-remote-login/confirm',{'state':flow['state'],'email':'fixture@example.test','organization_id':'fixture-org','confirm':True})[0]==400
   if not args.release:
    review=api('claude-remote-login','complete',{'state':flow['state'],'code':'fixture-code#'+flow['state']});assert review['email']=='fixture@example.test'
    assert not list(auth.glob('claude-*.json')),'saved before confirmation'
    assert 'fixture-claude-access' not in json.dumps(review)
    api('claude-remote-login','confirm',{'state':flow['state'],'email':review['email'],'organization_id':review['organization_id'],'confirm':True})
    saved=list(auth.glob('claude-*.json'));assert len(saved)==1
    record=json.loads(saved[0].read_text());assert record['refresh_token']=='fixture-claude-refresh'
   else:api('claude-remote-login','cancel',{'state':flow['state']})
   review=api('zai-provider','key/preview',{'id':'fixture-work','name':'Fixture work','key':'fixture-zai-private-key','billing':'coding'})
   assert 'fixture-zai-private-key' not in json.dumps(review) and not list(auth.glob('zai-*.json'))
   assert request('/v0/management/plugins/zai-provider/key/confirm',{'state':review['state']})[0]==400
   if args.release:api('zai-provider','key/cancel',{'state':review['state']})
   else:
    api('zai-provider','key/confirm',{'state':review['state'],'confirm':True});saved=list(auth.glob('zai-*.json'));assert len(saved)==1
    again=api('zai-provider','key/preview',{'id':'fixture-work','name':'Duplicate','key':'fixture-replacement-key','billing':'coding'})
    assert request('/v0/management/plugins/zai-provider/key/confirm',{'state':again['state'],'confirm':True})[0]==409
    api('zai-provider','key/cancel',{'state':again['state']})
    assert json.loads(saved[0].read_text())['api_key']=='fixture-zai-private-key'
    def proxy(path,body=None):
     req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Authorization':'Bearer fixture-proxy-key','Content-Type':'application/json'})
     with urllib.request.urlopen(req,timeout=15) as response:return response.read()
    for _ in range(50):
     if b'fixture-glm-model' in proxy('/v1/models'):break
     time.sleep(.1)
    else:raise AssertionError('Native model discovery did not expose fixture model')
    for stream in (False,True):
     reply=proxy('/v1/chat/completions',{'model':'fixture-glm-model','messages':[{'role':'user','content':'synthetic test'}],'stream':stream})
     assert b'fixture reply' in reply,(stream,reply)
     assert b'"error"' not in reply,(stream,reply)
     if stream:assert b'[DONE]' in reply,reply
    print('PASS: native model discovery, inference and streaming with synthetic provider transport',flush=True)
   if args.browser:
    assert not args.release,'Browser fixture test must not use the live provider transport'
    subprocess.run(['node',str(ROOT/'tests/provider_plugins.cjs')],env={**os.environ,'PROVIDERS_BASE':base},cwd=ROOT,check=True,timeout=150)
   print('PASS: '+('release' if args.release else 'fixture')+' DLL loading, protected routes, native account review/save and safe duplicate handling',flush=True)
  finally:
   proc.terminate()
   try:proc.wait(timeout=10)
   except subprocess.TimeoutExpired:proc.kill();proc.wait()
