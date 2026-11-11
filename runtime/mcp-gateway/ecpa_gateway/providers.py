"""API-key provider routes consumed by the native CLIProxyAPI executor, not MCP."""
import asyncio
import json
import re
import anyio

from starlette.responses import JSONResponse, StreamingResponse
from . import service_api
from .security import SafeError, resolve, validate_url

PRESETS = {'xai':'https://api.x.ai/v1', 'zai-coding':'https://api.z.ai/api/coding/paas/v4',
           'openai-compatible':None}


def validate(service):
    if '--' in service['id']:
        raise SafeError('Provider profile IDs must not contain consecutive hyphens; this keeps model aliases unambiguous.')
    preset = service.get('provider_preset')
    if preset not in PRESETS:
        raise SafeError('Choose xAI, Z.ai Coding, or an explicitly configured OpenAI-compatible provider.')
    url = service.get('provider_url', '')
    validate_url(url)
    if not url.startswith('https://') or url.endswith('/'):
        raise SafeError('Provider API base must use HTTPS without a trailing slash.')
    if PRESETS[preset] and url != PRESETS[preset]:
        raise SafeError('Provider destination does not match the selected preset.')
    models = service.get('models', [])
    if not isinstance(models, list) or not 1 <= len(models) <= 30:
        raise SafeError('Configure between one and thirty explicit model aliases.')
    aliases = set()
    for item in models:
        if set(item) != {'alias','model'} or not re.fullmatch('[a-z][a-z0-9-]{0,31}', item['alias']) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}',item['model']):
            raise SafeError('Use a short lowercase alias and an explicit upstream model ID.')
        if '--' in item['alias']:
            raise SafeError('Model aliases must not contain consecutive hyphens.')
        if item['alias'] in aliases:
            raise SafeError('Model aliases must be unique within an account profile.')
        aliases.add(item['alias'])
    if service.get('enabled') and service.get('core_access_confirmed') is not True:
        raise SafeError('Confirm that these models are available to clients authorized by this CLIProxyAPI core. MCP grants do not govern model requests.')


def alias(service, model):
    return 'ecpa-'+service['id']+'--'+model['alias']


def model_catalogue(registry):
    result = []
    for service in registry.load()[0]['services']:
        if service['kind'] != 'provider' or not service.get('enabled'):
            continue
        for model in service['models']:
            name = alias(service, model)
            result.append({'ID':name,'Object':'model','OwnedBy':'ecpa-managed',
                           'DisplayName':service['name']+' / '+model['alias'],'Name':name})
    return {'Provider':'ecpa-managed','Models':result}


async def verify(service, config):
    data = await service_api.request(service, config, 'GET', service['provider_url']+'/models')
    available = {m.get('id') for m in data.get('data', []) if isinstance(m, dict)}
    if not available or any(m['model'] not in available for m in service['models']):
        raise SafeError('The provider did not list every configured model. Check the API base, key permissions and exact model IDs; no fallback model was selected.')
    return {'models':[{'alias':alias(service,m),'model':m['model']} for m in service['models']]}


async def execute(controller, body):
    selected = None
    for service in controller.registry.load()[0]['services']:
        if service['kind']=='provider' and service.get('enabled'):
            for model in service['models']:
                if alias(service, model)==body.get('model'):
                    selected=(service,model)
    if selected is None:
        raise SafeError('Provider profile or model is disabled or unknown. No fallback was attempted.')
    service, model = selected
    config = controller.config()
    if service.get('execution_host',config['host_id']) != config['host_id']:
        raise SafeError('Provider profile belongs to a different runtime host.')
    if body.get('format') not in ('openai','chat-completions','openai-chat-completions'):
        raise SafeError('The host must translate this request to chat-completions before execution.')
    payload = body.get('payload')
    if not isinstance(payload, dict) or not isinstance(payload.get('messages'), list):
        raise SafeError('Expected a translated chat-completions payload.')
    payload = {**payload,'model':model['model'],'stream':body.get('stream') is True}
    value = await resolve(service['credential_refs'][0]['reference'], config)
    await controller.limit.acquire()
    http = service_api.client()
    response = None
    transferred = False
    try:
        request = http.build_request('POST', service['provider_url']+'/chat/completions',
                                    headers={'Authorization':'Bearer '+value}, json=payload)
        response = await http.send(request, stream=True)
        if response.status_code != 200:
            raise SafeError('Provider rejected this account/model request. No alternate account or model was tried.')
        if payload['stream']:
            if 'text/event-stream' not in response.headers.get('content-type',''):
                raise SafeError('Provider did not return the requested event stream.')
            closed=False
            async def close():
                nonlocal closed
                if closed:return
                closed=True
                with anyio.CancelScope(shield=True):
                    try:
                        try:await response.aclose()
                        finally:await http.aclose()
                    finally:controller.limit.release()
            class OwnedStream(StreamingResponse):
                async def __call__(self, scope, receive, send):
                    try:await super().__call__(scope,receive,send)
                    finally:await close()
            async def chunks():
                outcome='error'
                try:
                    size=0
                    async with asyncio.timeout(300):
                        buffer=b''
                        async for chunk in response.aiter_bytes():
                            size+=len(chunk);buffer+=chunk
                            if size>16*1024*1024 or len(buffer)>2*1024*1024:
                                raise SafeError('Provider stream exceeded its limit.')
                            while b'\n' in buffer:
                                line,buffer=buffer.split(b'\n',1)
                                yield service_api.scrub_event(line, value)
                        if buffer:yield service_api.scrub_event(buffer, value)
                    outcome='ok'
                except Exception:
                    yield b'data: {"error":{"message":"Provider stream interrupted; no automatic retry was made."}}\n\n'
                finally:
                    await close()
                    controller.activity({'client':'cliproxy-core','profile':service['id'],'host':config['host_id'],'tool':'provider-stream','outcome':outcome})
            result=OwnedStream(chunks(), media_type='text/event-stream', headers={'Cache-Control':'no-store'})
            transferred=True
            return result
        raw=b''
        async with asyncio.timeout(300):
            async for chunk in response.aiter_bytes():
                raw+=chunk
                if len(raw)>2*1024*1024:raise SafeError('Provider response exceeded its size limit.')
        data=service_api.scrub_value(json.loads(raw), value)
        controller.activity({'client':'cliproxy-core','profile':service['id'],'host':config['host_id'],'tool':'provider-request','outcome':'ok'})
        return JSONResponse(data, headers={'Cache-Control':'no-store'})
    except SafeError:
        raise
    except Exception:
        raise SafeError('Provider request failed; upstream details were suppressed and no fallback was attempted.') from None
    finally:
        # A streaming response owns the open connection until its iterator finishes.
        if not transferred:
            try:
                if response is not None:await response.aclose()
                await http.aclose()
            finally:controller.limit.release()
