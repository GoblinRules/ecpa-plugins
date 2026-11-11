import asyncio
import copy
import json
import time

import httpx
import pytest
from ecpa_gateway.app import Controller
from ecpa_gateway import service_api, providers, ssh
from ecpa_gateway.registry import validate_service, encode, atomic
from ecpa_gateway.security import SafeError
from test_gateway import config, live, publish, mcp_call


def profile(kind, name='work'):
    binding={'cloudflare':('env','CLOUDFLARE_API_TOKEN'),'runway':('env','RUNWAYML_API_SECRET'),'provider':('header','Authorization')}
    s={'id':name,'name':name,'kind':kind,'enabled':False,'allowed_tools':[], 'execution_host':'test-runtime','credential_refs':[]}
    if kind in binding:
        mode,key=binding[kind]
        s['credential_refs']=[{'kind':mode,'name':key,'reference':{'provider':'bitwarden','region':'eu','secret_id':'11111111-1111-1111-1111-111111111111'}}]
    if kind=='cloudflare':s.update(account_id='a'*32,service='cloudflare')
    if kind=='runway':s['allow_video_requests']=True
    if kind=='provider':s.update(provider_preset='xai',provider_url='https://api.x.ai/v1',models=[{'alias':'primary','model':'fixture-model'}])
    if kind=='ssh':s.update(machine_id='fixture-machine',ssh_operations={'restart-web':{'action':'restart-service','service':'nginx'}})
    return s


@pytest.fixture
def upstream(monkeypatch):
    requests=[];values={};state={'wrong_account':False,'redirect':False,'deny':False}
    async def resolve(reference, config):
        return values.get(reference['secret_id'],'fixture-service-value')
    async def handle(request):
        requests.append(request)
        if state['redirect']:return httpx.Response(302,headers={'Location':'https://other.example/steal'})
        if state['deny']:return httpx.Response(401,json={'error':'fixture-service-value'})
        path=request.url.path
        if request.url.host=='api.cloudflare.com':
            account=path.split('/accounts/')[-1].split('/')[0]
            if path.endswith('/zones'):
                account='b'*32 if state['wrong_account'] else request.url.params['account.id']
                result=[{'id':'zone','name':'example.test','account':{'id':account},'secret':'fixture-service-value'}]
            elif path.endswith('/workers/scripts'):result=[{'id':'worker-one','bindings':{'secret':'fixture-service-value'}}]
            else:result={'id':account,'name':'Account '+account[:1]}
            return httpx.Response(200,json={'success':True,'result':result})
        if path.endswith('/organization'):return httpx.Response(200,json={'creditBalance':10,'tier':{'name':'test'}})
        if path.endswith('/text_to_video'):return httpx.Response(200,json={'id':'33333333-3333-4333-8333-333333333333'})
        if '/tasks/' in path:return httpx.Response(200,json={'id':path.split('/')[-1],'status':'SUCCEEDED','output':['https://output.example/video.mp4']})
        if path.endswith('/models'):return httpx.Response(200,json={'data':[{'id':'fixture-model'}]})
        if path.endswith('/chat/completions'):
            payload=json.loads(request.content)
            assert payload['model']=='fixture-model'
            if payload.get('stream'):
                chunk={'id':'chatcmpl-fixture','object':'chat.completion.chunk','created':0,'model':'fixture-model','choices':[{'index':0,'delta':{'role':'assistant','content':'fixture reply'},'finish_reason':None}]}
                stop={**chunk,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}
                return httpx.Response(200,headers={'Content-Type':'text/event-stream'},content=('data: '+json.dumps(chunk)+'\n\ndata: '+json.dumps(stop)+'\n\ndata: [DONE]\n\n').encode())
            return httpx.Response(200,json={'id':'chatcmpl-fixture','object':'chat.completion','created':0,'model':'fixture-model','choices':[{'index':0,'message':{'role':'assistant','content':'fixture reply'},'finish_reason':'stop'}],'usage':{'prompt_tokens':1,'completion_tokens':2,'total_tokens':3}})
        raise AssertionError('Unexpected upstream destination')
    monkeypatch.setattr(service_api,'resolve',resolve);monkeypatch.setattr(providers,'resolve',resolve)
    monkeypatch.setattr(service_api,'client',lambda:httpx.AsyncClient(transport=httpx.MockTransport(handle),follow_redirects=False,trust_env=False))
    return requests,values,state


async def test_cloudflare_account_isolation_and_read_boundaries(config,upstream):
    c=Controller(config);requests,values,state=upstream
    a=profile('cloudflare','personal');b=profile('cloudflare','work');b['account_id']='b'*32
    b['credential_refs'][0]['reference']['secret_id']='22222222-2222-2222-2222-222222222222'
    values.update({'11111111-1111-1111-1111-111111111111':'fixture-personal','22222222-2222-2222-2222-222222222222':'fixture-work'})
    await publish(c,a,('account','zones','workers'));await publish(c,b,('account','zones','workers'))
    results=await asyncio.gather(c.call('codex','personal__zones',{}),c.call('codex','work__workers',{}))
    assert not any(r.isError for r in results)
    assert all(r.method=='GET' and r.url.host=='api.cloudflare.com' for r in requests)
    assert requests[-2].headers['Authorization']=='Bearer fixture-personal'
    assert requests[-1].headers['Authorization']=='Bearer fixture-work'
    assert 'secret' not in results[1].content[0].text
    count=len(requests)
    assert (await c.call('codex','personal__zones',{'account_id':'b'*32})).isError
    assert (await c.call('codex','personal__delete',{})).isError
    assert len(requests)==count
    state['wrong_account']=True
    assert (await c.call('codex','personal__zones',{})).isError
    state['redirect']=True
    assert (await c.call('codex','personal__account',{})).isError
    assert requests[-1].url.host=='api.cloudflare.com'


async def test_paid_requests_require_single_use_approval_and_owner(config,upstream):
    c=Controller(config);requests,_,_=upstream
    await publish(c,profile('runway'),('organization','task','request_video','request_status'))
    args={'prompt':'Synthetic fixture only','duration':2,'ratio':'1280:720'}
    result=await c.call('codex','work__request_video',args);record=json.loads(result.content[0].text)
    assert not any(r.method=='POST' for r in requests)
    with pytest.raises(SafeError):c.approvals.status('claude','work',record['request_id'])
    with pytest.raises(SafeError):await c.admin({'action':'approve-request','id':record['request_id']})
    outputs=await asyncio.gather(*(c.admin({'action':'approve-request','id':record['request_id'],'confirm':True}) for _ in range(2)),return_exceptions=True)
    assert sum(isinstance(x,SafeError) for x in outputs)==1
    assert sum(r.method=='POST' for r in requests)==1
    assert c.approvals.status('codex','work',record['request_id'])['status']=='completed'
    # Persistent claim/result survives a restart and cannot be replayed.
    c=Controller(config)
    with pytest.raises(SafeError):await c.admin({'action':'approve-request','id':record['request_id'],'confirm':True})
    assert 'fixture-service-value' not in c.approvals.path.read_text()
    activity=(c.registry.dir/'mcp-activity.jsonl').read_text()
    assert args['prompt'] not in activity and 'fixture-service-value' not in activity
    second=json.loads((await c.call('codex','work__request_video',args)).content[0].text)
    cfg=c.config();cfg['identities']['codex']['services']=[];atomic(c.config_path,encode(cfg))
    with pytest.raises(SafeError):await c.admin({'action':'approve-request','id':second['request_id'],'confirm':True})


async def test_provider_routes_have_separate_auth_rotation_and_no_fallback(live,upstream):
    requests,values,state=upstream
    s=profile('provider');review=await live.admin({'action':'test','service':s})
    assert review['models'][0]['alias']=='ecpa-work--primary'
    _,version=live.registry.load()
    with pytest.raises(SafeError):await live.admin({'action':'publish','review':review['review'],'version':version})
    await live.admin({'action':'publish','review':review['review'],'version':version,'confirm_core_access':True})
    assert not (await mcp_call(live.config(),'codex')).tools
    assert providers.model_catalogue(live.registry)['Models'][0]['ID']=='ecpa-work--primary'
    url=live.config()['url'].removesuffix('/mcp')+'/provider'
    body={'model':'ecpa-work--primary','format':'openai','stream':False,'payload':{'messages':[{'role':'user','content':'fixture'}],'model':'malicious-route'}}
    async with httpx.AsyncClient(trust_env=False) as http:
        assert (await http.post(url,json=body,headers={'Authorization':'Bearer fixture-codex'})).status_code==401
        reply=await http.post(url,json=body,headers={'Authorization':'Bearer fixture-admin'});assert reply.status_code==200
        values['11111111-1111-1111-1111-111111111111']='fixture-rotated'
        reply=await http.post(url,json={**body,'stream':True},headers={'Authorization':'Bearer fixture-admin'})
        assert '[DONE]' in reply.text and requests[-1].headers['Authorization']=='Bearer fixture-rotated'
        count=len(requests)
        assert (await http.post(url,json={**body,'model':'unknown'},headers={'Authorization':'Bearer fixture-admin'})).status_code==502
        assert len(requests)==count
        state['deny']=True
        reply=await http.post(url,json=body,headers={'Authorization':'Bearer fixture-admin'})
        assert reply.status_code==502 and 'fixture-service-value' not in reply.text
        assert len(requests)==count+1
    assert 'fixture-rotated' not in live.registry.path.read_text()


async def test_ssh_approval_binds_machine_and_predefined_operation(config,monkeypatch):
    c=Controller(config);calls=[];revision='a'*64
    async def snapshot(service,config):return {'revision':revision}
    async def operation(service,config,name):
        if service['machine_revision']!=revision:raise SafeError('Changed machine')
        calls.append(name);return {'operation':name,'machine_id':service['machine_id']}
    monkeypatch.setattr(ssh,'snapshot',snapshot);monkeypatch.setattr(ssh,'operation',operation)
    await publish(c,profile('ssh'),('diagnostics','request_operation','request_status'))
    assert calls==['diagnostics']
    record=json.loads((await c.call('codex','work__request_operation',{'operation':'restart-web'})).content[0].text)
    assert calls==['diagnostics']
    revision='b'*64
    result=await c.admin({'action':'approve-request','id':record['request_id'],'confirm':True})
    assert result['status']=='failed' and calls==['diagnostics']
    assert (await c.call('codex','work__request_operation',{'operation':'shell','command':'anything'})).isError
    invalid=profile('ssh');invalid['ssh_operations']['restart-web']['service']='nginx; command'
    with pytest.raises(SafeError):validate_service(invalid)


async def test_approval_expiry_profile_edits_and_running_claim(config,upstream):
    c=Controller(config)
    await publish(c,profile('runway'),('organization','request_video','request_status'))
    args={'prompt':'Fixture','duration':2,'ratio':'1280:720'}
    async def propose():
        return json.loads((await c.call('codex','work__request_video',args)).content[0].text)['request_id']
    expired=await propose()
    records=c.approvals.load();records[-1]['expires']=0;atomic(c.approvals.path,encode(records))
    assert c.approvals.status('codex','work',expired)['status']=='expired'
    with pytest.raises(SafeError):await c.approvals.decide(expired,True,True)
    changed=await propose();s=c.registry.selected('work');s['name']='Changed'
    c.registry.save(s,c.registry.load()[1])
    with pytest.raises(SafeError):await c.approvals.decide(changed,True,True)
    running=await propose();records=c.approvals.load();records[-1]['status']='running';atomic(c.approvals.path,encode(records))
    with pytest.raises(SafeError):await Controller(config).approvals.decide(running,True,True)
    assert not any(r.method=='POST' for r in upstream[0])


async def test_wrangler_requests_bind_workspace_and_account(config,upstream,monkeypatch):
    import sys
    from ecpa_gateway import jobs
    c=Controller(config);root=config.parent/'workspace';root.mkdir()
    (root/'wrangler.jsonc').write_text('{}',encoding='utf-8')
    entry=config.parent/'wrangler-fixture.py';entry.write_text('# fixture',encoding='utf-8')
    cfg=c.config();cfg['workspaces']={'website':str(root)};atomic(config,encode(cfg))
    s=profile('cloudflare');s['wrangler']={'node_executable':sys.executable,'entrypoint':str(entry),'workspace_ids':['website'],'agent_operations':['verify','dry-run','deploy']}
    await publish(c,s,('account','request_wrangler','request_status'))
    calls=[]
    async def run(service,cfg,workspace,op,*,approved=False):
        assert approved;calls.append((service['account_id'],workspace,op));return {'exit_code':0}
    monkeypatch.setattr(jobs,'run_wrangler',run)
    async def propose():return json.loads((await c.call('codex','work__request_wrangler',{'workspace_id':'website','operation':'deploy'})).content[0].text)['request_id']
    first=await propose();assert not calls
    (root/'source.js').write_text('// changed after request',encoding='utf-8')
    assert (await c.approvals.decide(first,True,True))['status']=='failed' and not calls
    second=await propose()
    assert (await c.approvals.decide(second,True,True))['status']=='completed'
    assert calls==[('a'*32,'website','deploy')]
    with pytest.raises(SafeError):await c.approvals.decide(second,True,True)
    assert (await c.call('codex','work__request_wrangler',{'workspace_id':'unassigned','operation':'deploy'})).isError
    assert (await c.call('codex','work__request_wrangler',{'workspace_id':'website','operation':'shell'})).isError


async def test_provider_escaped_secret_stream_cleanup(config,monkeypatch):
    c=Controller(config);secret='fixture-quote-"-slash-\\'
    s=profile('provider');s.update(enabled=True,core_access_confirmed=True)
    c.registry.save(s,c.registry.load()[1])
    async def resolve(*_):return secret
    monkeypatch.setattr(providers,'resolve',resolve)
    closed=[]
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            raw=('data: '+json.dumps({'choices':[{'delta':{'content':secret}}]})+'\n\ndata: [DONE]\n\n').encode()
            for i in range(0,len(raw),3):yield raw[i:i+3]
        async def aclose(self):closed.append(True)
    def respond(request):return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Stream())
    monkeypatch.setattr(service_api,'client',lambda:httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    body={'model':'ecpa-work--primary','format':'openai','stream':True,'payload':{'messages':[]}}
    before=c.limit._value
    response=await providers.execute(c,body)
    out=b''.join([item async for item in response.body_iterator]).decode()
    assert '[REDACTED]' in out and json.dumps(secret)[1:-1] not in out and c.limit._value==before and closed
    response=await providers.execute(c,body)
    await anext(response.body_iterator)
    await response.body_iterator.aclose()
    assert c.limit._value==before and len(closed)==2
    response=await providers.execute(c,body)
    async def disconnected_send(message):raise OSError('synthetic client disconnect before body starts')
    async def receive():return {'type':'http.disconnect'}
    with pytest.raises(Exception):await response({'type':'http','asgi':{'spec_version':'2.4'}},receive,disconnected_send)
    assert c.limit._value==before and len(closed)==3
    assert service_api.scrub_value(json.loads(json.dumps({'echo':secret})),secret)=={'echo':'[REDACTED]'}


def test_bootstrap_vault_namespace_cannot_be_bound_to_services():
    from ecpa_gateway.security import validate_reference
    for target in ['ECPA/MCP/fixture/admin','ECPA/mcp/fixture/bws']:
        with pytest.raises(SafeError):validate_reference({'provider':'windows-vault','target':target})


def test_editor_removes_old_optional_policy_without_losing_extensions(config):
    c=Controller(config)
    s=profile('runway');s['extension_note']='preserve me'
    c.registry.save(s,c.registry.load()[1])
    edited=profile('runway');edited.pop('allow_video_requests')
    c.registry.save(edited,c.registry.load()[1])
    saved=c.registry.selected('work')
    assert 'allow_video_requests' not in saved and saved['extension_note']=='preserve me'
