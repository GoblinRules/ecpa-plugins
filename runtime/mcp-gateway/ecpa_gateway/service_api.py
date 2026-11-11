"""Small reviewed API adapters. Destinations and operations are never tool arguments."""
import json
import re
import asyncio

import httpx
from .security import SafeError, resolve, redact

CF = 'https://api.cloudflare.com/client/v4'
RUNWAY = 'https://api.dev.runwayml.com/v1'


def client():
    return httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False)


def scrub_value(data, secret):
    """Scrub decoded values, including JSON-escaped echoes and object keys."""
    if isinstance(data, str):return data.replace(secret, '[REDACTED]')
    if isinstance(data, list):return [scrub_value(item, secret) for item in data]
    if isinstance(data, dict):return {scrub_value(key, secret):scrub_value(value, secret) for key,value in data.items()}
    return data


def scrub_event(line, secret):
    text=line.decode('utf-8')
    if text.startswith('data:'):
        value=text[5:].strip()
        if value=='[DONE]':return b'data: [DONE]\n'
        # Malformed JSON is suppressed, never passed through as an error echo.
        return ('data: '+json.dumps(scrub_value(json.loads(value),secret))+'\n').encode()
    # Standard non-data SSE fields may contain upstream echoes too.
    return (text.replace(secret,'[REDACTED]')+'\n').encode()


async def request(service, config, method, url, *, params=None, payload=None):
    value = await resolve(service['credential_refs'][0]['reference'], config)
    headers = {'Authorization': 'Bearer '+value, 'Accept': 'application/json'}
    if service['kind'] == 'runway':
        headers['X-Runway-Version'] = '2024-11-06'
    try:
        async with asyncio.timeout(45), client() as http:
            async with http.stream(method, url, headers=headers, params=params, json=payload) as response:
                if response.status_code >= 300:
                    raise SafeError('Service rejected the request. Check the selected account, permissions, quota and credential reference.')
                raw = b''
                async for chunk in response.aiter_bytes():
                    raw += chunk
                    if len(raw) > 2*1024*1024:
                        raise SafeError('Service response exceeded its size limit.')
        # Scrub known credentials before parsing, even if upstream echoed them.
        result = scrub_value(json.loads(raw), value)
        if not isinstance(result, dict):
            raise ValueError()
        return redact(result)
    except SafeError:
        raise
    except Exception:
        raise SafeError('Service response was unavailable or invalid; upstream details were suppressed.') from None


def schema(properties=None, required=None):
    return {'type':'object', 'properties':properties or {}, 'required':required or [], 'additionalProperties':False}


def tool(name, description, properties=None, required=None, read_only=True):
    return {'name':name, 'description':description, 'inputSchema':schema(properties, required),
            'annotations':{'readOnlyHint':read_only, 'destructiveHint':False, 'openWorldHint':True}}


PAGE = {'page':{'type':'integer','minimum':1,'maximum':1000}}
REQUEST_ID = {'request_id':{'type':'string','pattern':'^[a-f0-9]{32}$'}}
VIDEO = {'prompt':{'type':'string','minLength':1,'maxLength':1000},
         'duration':{'type':'integer','minimum':2,'maximum':10},
         'ratio':{'type':'string','enum':['1280:720','720:1280']}}


def tools(service):
    if service['kind'] == 'cloudflare':
        result = [tool('account', 'Read the explicitly bound Cloudflare account.'),
                tool('zones', 'List zones belonging to this account, 50 per page.', PAGE),
                tool('workers', 'List Worker metadata in this account; no source code or bindings.')]
        settings=service.get('wrangler',{})
        if settings.get('agent_operations'):
            result += [tool('request_wrangler','Request a fixed Wrangler operation on a trusted workspace. Requires human approval in ECPA; deploy changes Cloudflare resources.',
                {'workspace_id':{'type':'string','enum':settings['workspace_ids']},'operation':{'type':'string','enum':settings['agent_operations']}},['workspace_id','operation'],False),
                tool('request_status','Read your own operation request status.',REQUEST_ID,['request_id'])]
        return result
    if service['kind'] == 'runway':
        result = [tool('organization', 'Read the organization credit balance and usage tier. No generation.'),
                  tool('task', 'Read one task accessible to this account; never cancels or deletes it.',
                       {'task_id':{'type':'string','format':'uuid','pattern':'^[a-fA-F0-9-]{36}$'}}, ['task_id'])]
        if service.get('allow_video_requests'):
            result += [tool('request_video', 'Request a gen4.5 video. Requires a separate human approval in ECPA before any paid request.', VIDEO, ['prompt','duration','ratio'], False),
                       tool('request_status', 'Read your own approval request status.', REQUEST_ID, ['request_id'])]
        return result
    if service['kind'] == 'ssh':
        result = [tool('diagnostics', 'Run fixed OS/user diagnostics using the saved machine and verified host key.')]
        if service.get('ssh_operations'):
            result += [tool('request_operation', 'Request a predefined machine operation. A human must approve the exact operation in ECPA.',
                            {'operation':{'type':'string','enum':list(service['ssh_operations'])}}, ['operation'], False),
                       tool('request_status', 'Read your own machine operation request status.', REQUEST_ID, ['request_id'])]
        return result
    raise SafeError('Unknown built-in adapter.')


async def read(service, config, name, arguments):
    if service['kind'] == 'cloudflare':
        account = service['account_id']
        if name == 'account':
            data = await request(service, config, 'GET', CF+'/accounts/'+account)
            result = data.get('result', {})
            if data.get('success') is not True or result.get('id') != account:
                raise SafeError('Cloudflare returned a different account or denied the operation.')
            return {k:result[k] for k in ('id','name','type') if k in result}
        if name == 'zones':
            data = await request(service, config, 'GET', CF+'/zones', params={'account.id':account,'page':arguments.get('page',1),'per_page':50})
            fields = ('id','name','status','paused','type')
        elif name == 'workers':
            data = await request(service, config, 'GET', CF+'/accounts/'+account+'/workers/scripts')
            fields = ('id','created_on','modified_on')
        else:
            raise SafeError('Cloudflare operation is not implemented.')
        if data.get('success') is not True or not isinstance(data.get('result'), list):
            raise SafeError('Cloudflare did not confirm the read operation.')
        records = data['result']
        if name == 'zones' and any(item.get('account',{}).get('id') != account for item in records):
            raise SafeError('Cloudflare returned a zone outside the selected account.')
        return {'account_id':account,'items':[{k:item[k] for k in fields if k in item} for item in records[:500]],
                'page':arguments.get('page',1),'truncated':len(records)>500}
    if service['kind'] == 'runway':
        if name == 'organization':
            data = await request(service, config, 'GET', RUNWAY+'/organization')
            return {k:data[k] for k in ('creditBalance','usage','tier') if k in data}
        if name == 'task' and re.fullmatch('[a-fA-F0-9-]{36}',arguments.get('task_id','')):
            data = await request(service, config, 'GET', RUNWAY+'/tasks/'+arguments['task_id'])
            return {k:data[k] for k in ('id','status','createdAt','progress','output','failureCode') if k in data}
    raise SafeError('Operation is not a supported read.')


async def verify(service, config):
    if service['kind'] == 'cloudflare':
        await read(service, config, 'account', {})
    elif service['kind'] == 'runway':
        await read(service, config, 'organization', {})
    else:
        from .ssh import snapshot, operation
        # Retesting is the explicit review path after a machine edit.
        service.pop('machine_revision',None)
        service['machine_revision']=(await snapshot(service, config))['revision']
        await operation(service, config, 'diagnostics')
    return tools(service)
