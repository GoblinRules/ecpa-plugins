"""Short, explicit operations with single-use human approval; not a job scheduler."""
import copy
import json
import time
import uuid

import portalocker
from .registry import atomic, encode, digest, reject_literals
from .security import SafeError
from . import service_api


class Approvals:
    def __init__(self, controller):
        self.controller = controller
        self.path = controller.registry.dir/'mcp-requests.json'

    def lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return portalocker.Lock(str(self.path)+'.lock', timeout=3)

    def load(self):
        if not self.path.exists():return []
        raw=self.path.read_bytes()
        if len(raw)>2*1024*1024:raise SafeError('Approval history reached its size limit. Archive it privately before adding requests.')
        return json.loads(raw)

    def propose(self, identity, service, tool, arguments):
        reject_literals(arguments)
        record={'id':uuid.uuid4().hex, 'client':identity, 'profile':service['id'], 'tool':tool,
                'arguments':copy.deepcopy(arguments), 'revision':digest(encode(service)),
                'status':'pending', 'created':time.time(), 'expires':time.time()+900,
                'host':self.controller.config()['host_id']}
        record['client_fingerprint']=self.controller.config()['identities'].get(identity,{}).get('sha256')
        if tool=='request_wrangler':
            from .jobs import approval_context
            record['target']=approval_context(service,self.controller.config(),arguments['workspace_id'],arguments['operation'])
        with self.lock():
            records=self.load()
            pending=[r for r in records if r['status']=='pending' and r['expires']>time.time()]
            if len(pending)>=32 or sum(r['client']==identity for r in pending)>=5:
                raise SafeError('Pending request limit reached. Finish or reject an existing request first.')
            # Retain a bounded history, without discarding active requests.
            records=[r for r in records if r in pending]+[r for r in records if r not in pending][-60:]
            records.append(record);atomic(self.path,encode(records))
        return {'request_id':record['id'],'status':'pending','expires':record['expires'],
                'message':'Review and approve this exact request in ECPA. Nothing has been executed.'}

    def status(self, identity, profile, request_id):
        with self.lock():
            record=next((r for r in self.load() if r['id']==request_id and r['client']==identity and r['profile']==profile),None)
        if not record:raise SafeError('Request not found for this client and profile.')
        result={k:record[k] for k in ('id','status','host','profile','expires')}
        if result['status']=='pending' and result['expires']<time.time():result['status']='expired'
        if 'result' in record:result['result']=record['result']
        return result

    def inventory(self):
        with self.lock():records=self.load()
        return [{**r,'status':'expired' if r['status']=='pending' and r['expires']<time.time() else r['status']} for r in records]

    async def decide(self, request_id, approve, confirm):
        if approve and confirm is not True:raise SafeError('Review the exact target and operation, then explicitly approve it.')
        with self.lock():
            records=self.load();record=next((r for r in records if r['id']==request_id),None)
            if not record or record['status']!='pending' or record['expires']<time.time():
                raise SafeError('Request is missing, expired or already attempted. It will not run again.')
            service=self.controller.registry.selected(record['profile'])
            if approve and (digest(encode(service))!=record['revision'] or not self.controller.permitted(service,record['client']) or record['tool'] not in service.get('allowed_tools',[]) or self.controller.config()['identities'].get(record['client'],{}).get('sha256')!=record.get('client_fingerprint')):
                raise SafeError('Profile, tools or client access changed. Reject this request and submit a new one.')
            record['status']='running' if approve else 'rejected'
            atomic(self.path,encode(records))
        if not approve:return {'id':request_id,'status':'rejected'}
        # Persist the claim BEFORE starting. Crashes/timeouts are never retried automatically.
        status='failed';result={'message':'Operation failed or its completion is uncertain. Verify upstream before requesting another attempt.'}
        try:
            async with self.controller.limit:
                # Recheck after waiting for capacity; revocation while queued wins.
                current=self.controller.registry.selected(record['profile'])
                if digest(encode(current))!=record['revision'] or not self.controller.permitted(current,record['client']) or self.controller.config()['host_id']!=record['host'] or self.controller.config()['identities'].get(record['client'],{}).get('sha256')!=record.get('client_fingerprint'):
                    raise SafeError('Profile, host or grants changed before execution.')
                if service['kind']=='runway' and record['tool']=='request_video':
                    args=record['arguments']
                    if len(args['prompt'].encode('utf-16-le'))//2>1000:raise SafeError('Runway prompt exceeds its UTF-16 length limit.')
                    response=await service_api.request(service,self.controller.config(),'POST',service_api.RUNWAY+'/text_to_video',
                        payload={'model':'gen4.5','promptText':args['prompt'],'duration':args['duration'],'ratio':args['ratio']})
                    if not isinstance(response.get('id'),str):raise SafeError('Runway did not return a task ID; check upstream before retrying.')
                    result={'task_id':response['id']}
                elif service['kind']=='ssh' and record['tool']=='request_operation':
                    from .ssh import operation
                    result=await operation(service,self.controller.config(),record['arguments']['operation'])
                elif service['kind']=='cloudflare' and record['tool']=='request_wrangler':
                    from .jobs import approval_context, run_wrangler
                    args=record['arguments'];cfg=self.controller.config()
                    if approval_context(service,cfg,args['workspace_id'],args['operation'])!=record['target']:
                        raise SafeError('Workspace or configuration changed since the request.')
                    result=await run_wrangler(service,cfg,args['workspace_id'],args['operation'],approved=True)
                    if result['exit_code']!=0:raise SafeError('Wrangler exited unsuccessfully; inspect upstream before retrying.')
                else:raise SafeError('Approved operation is not implemented.')
                status='completed'
        except Exception:
            pass
        finally:
            with self.lock():
                records=self.load();record=next(r for r in records if r['id']==request_id)
                record.update(status=status,result=result);atomic(self.path,encode(records))
            self.controller.activity({'client':record['client'],'profile':service['id'],'host':record['host'],
                'tool':record['tool'],'request_id':request_id,'outcome':status})
        return {'id':request_id,'status':status,'result':result}
