"""Real-core and helper checks using synthetic, uniquely namespaced Windows credentials."""
import argparse, concurrent.futures, ctypes, hashlib, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--core',required=True);p.add_argument('--serve',action='store_true');a=p.parse_args()
ROOT=Path(__file__).resolve().parents[3];KEY='connections-isolated-test-key'
with tempfile.TemporaryDirectory(prefix='ecpa-connections-test-') as tmp:
 home=Path(tmp);data=home/'data';plugins=home/'plugins';plugins.mkdir();project=home/'project';project.mkdir()
 shutil.copy2(ROOT/'target/release/connections_manager.dll',plugins/'connections-manager.dll')
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 config={'host':'127.0.0.1','port':port,'auth-dir':str(home/'auth'),'remote-management':{'secret-key':KEY,'allow-remote':False,'disable-control-panel':True},'api-keys':['test-client-key'],'plugins':{'enabled':True,'dir':str(plugins),'configs':{'connections-manager':{'enabled':True,'data_dir':str(data)}}}}
 (home/'config.yaml').write_text(json.dumps(config),encoding='utf-8');base=f'http://127.0.0.1:{port}'
 def request(path,body=None,auth=True,method=None):
  req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+KEY} if auth else {})},method=method)
  try:
   with urllib.request.urlopen(req,timeout=15) as r:return r.status,r.read()
  except urllib.error.HTTPError as e:return e.code,e.read()
 def api(path,body=None):
  code,raw=request('/v0/management/connections-manager/'+path,body);assert code==200,(code,raw.decode());return json.loads(raw)
 helper=str(ROOT/'target/release/ecpa-connect.exe')
 def launch(selection,check):
  env={**os.environ,'GH_TOKEN':'parent-gh','CLOUDFLARE_API_TOKEN':'parent-cf','CLOUDFLARE_API_KEY':'parent-key','GITHUB_PERSONAL_ACCESS_TOKEN':'parent-mcp'}
  r=subprocess.run([helper,'--data-dir',str(data),'run',*selection,'--',sys.executable,'-c',check],capture_output=True,text=True,env=env,timeout=20)
  assert r.returncode==0,(r.returncode,r.stderr);assert 'synthetic-' not in r.stdout+r.stderr;return r
 targets=['gh-work','cf-work','cf-personal','browser-test']
 with (home/'core.log').open('wb') as log:
  process=subprocess.Popen([str(Path(a.core).resolve()),'-config',str(home/'config.yaml'),'--local-model'],cwd=home,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
  try:
   for _ in range(150):
    try:
     if request('/v0/management/connections-manager/state')[0]==200:break
    except OSError:pass
    if process.poll() is not None:raise RuntimeError((home/'core.log').read_text(errors='replace'))
    time.sleep(.1)
   else:raise RuntimeError('Core failed to become ready')
   state=api('state');assert not state['connections']
   assert request('/v0/management/connections-manager/state',auth=False)[0]==401
   code,page=request('/v0/resource/plugins/connections-manager/editor?token=unused',auth=False);assert code==200 and b'Connections Manager' in page
   assert request('/v0/resource/plugins/connections-manager/save',{'token':'synthetic-secret'},auth=False)[0]==404
   for id,service,account in [('gh-work','github',''),('cf-work','cloudflare','1'*32),('cf-personal','cloudflare','2'*32)]:
    state=api('save',{'version':state['version'],'connection':{'id':id,'name':id.replace('-',' ').title(),'service':service,'account_id':account},'token':'synthetic-'+id})
    assert 'synthetic-' not in json.dumps(state)
   assert 'synthetic-' not in (data/'connections.json').read_text()
   code,_=request('/v0/management/connections-manager/delete',{'version':'stale','id':'gh-work'});assert code==400
   state=api('assign',{'version':state['version'],'project':{'path':str(project),'github':'gh-work','cloudflare':'cf-work'}})
   code,_=request('/v0/management/connections-manager/delete',{'version':state['version'],'id':'gh-work'});assert code==400
   launch(['--project',str(project)],"import os;assert os.environ['GH_TOKEN']=='synthetic-gh-work';assert os.environ['GITHUB_PERSONAL_ACCESS_TOKEN']=='synthetic-gh-work';assert os.environ['CLOUDFLARE_API_TOKEN']=='synthetic-cf-work';assert 'CLOUDFLARE_API_KEY' not in os.environ;assert os.path.samefile(os.getcwd(),"+repr(str(project))+")")
   def single(id):return launch(['--connection',id],"import os;assert os.environ['CLOUDFLARE_API_TOKEN']=="+repr('synthetic-'+id)+";assert 'GH_TOKEN' not in os.environ")
   with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(single,['cf-work','cf-personal']))
   result=subprocess.run([helper,'--data-dir',str(data),'run','--connection','gh-work','--',sys.executable,'-c','import sys;sys.stdout.write(sys.stdin.read());sys.exit(7)'],input='stdio protocol fixture',capture_output=True,text=True)
   assert result.returncode==7 and result.stdout=='stdio protocol fixture' and 'synthetic-' not in result.stderr
   print('PASS: native plugin authentication, public-resource boundary, Windows vault, secret-free catalogue, stale-write rejection, project assignment, concurrent account isolation, stdio and exit-code forwarding',flush=True)
   if a.serve:
    print('CONNECTIONS_BASE='+base,flush=True);print('CONNECTIONS_PROJECT='+str(project),flush=True);process.wait()
   else:
    state=api('assign',{'version':state['version'],'project':{'path':str(project),'github':None,'cloudflare':None}})
    for id in targets[:3]:state=api('delete',{'version':state['version'],'id':id})
    assert not state['connections']
    assert request('/v0/management/plugins/connections-manager',method='DELETE')[0]==200
    assert process.poll() is None
    print('PASS: credential deletion and native plugin unload',flush=True)
  finally:
   process.terminate()
   try:process.wait(timeout=10)
   except subprocess.TimeoutExpired:process.kill();process.wait()
   cred=ctypes.WinDLL('Advapi32.dll',use_last_error=True);cred.CredDeleteW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32]
   namespace=hashlib.sha256(str(data).encode()).hexdigest()
   for id in targets:cred.CredDeleteW(f'ECPA/Connections/{namespace}/{id}',1,0)
