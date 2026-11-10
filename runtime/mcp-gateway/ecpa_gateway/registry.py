"""One managed MCP service catalogue, owned by Connections Manager.

Native ECPA and client configs are import sources / explicit gateway destinations,
not live replicas. Unknown catalogue keys survive edits and rollback.
"""
import copy
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path

import portalocker
import jsonschema
from .security import SafeError, validate_reference, validate_url, SENSITIVE, TOKEN_LITERAL, RUNTIME_ENV

ID = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
TOOL = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")
ENV = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
PORTAINER_TOOLS = ["portainer_environments", "portainer_stacks", "portainer_containers", "portainer_logs"]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False)+"\n").encode()


def atomic(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def reject_literals(value):
    if isinstance(value, dict):
        for k,v in value.items():
            if SENSITIVE.search(k) and k not in ("secret_id", "credential_refs") and v not in (None, "", [], {}):
                raise SafeError("Possible credential literal detected. Replace it with a credential reference.")
            reject_literals(v)
    elif isinstance(value, list):
        for v in value:
            reject_literals(v)
    elif isinstance(value, str) and TOKEN_LITERAL.search(value):
        raise SafeError("Possible credential literal detected. Replace it with a credential reference.")


def validate_schema(schema):
    def local_references(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('$ref','$dynamicRef','$recursiveRef') and (not isinstance(item,str) or not item.startswith('#')):
                    raise SafeError('Tool schemas must use local references; external schema retrieval is not permitted.')
                local_references(item)
        elif isinstance(value,list):
            for item in value:local_references(item)
    local_references(schema)
    try:jsonschema.validators.validator_for(schema).check_schema(schema)
    except Exception:raise SafeError('Connector supplied an invalid tool schema.') from None


def validate_service(s):
    if not isinstance(s,dict) or not ID.fullmatch(s.get("id", "")) or not isinstance(s.get("name"),str) or not 1 <= len(s["name"]) <= 100:
        raise SafeError("Supply a stable lowercase service ID and a display name.")
    if s.get("kind") not in ("portainer", "sample", "stdio", "http"):
        raise SafeError("Choose built-in Portainer, sample, installed stdio package or Streamable HTTP.")
    if not isinstance(s.get("enabled", False), bool):
        raise SafeError("Enabled must be boolean.")
    reject_literals(s)
    for key in ('access_group','execution_host'):
        if s.get(key) is not None and not ID.fullmatch(s[key]):raise SafeError('Use stable lowercase group and execution-host IDs.')
    if not isinstance(s.get('project_ids',[]),list) or any(not ID.fullmatch(x) for x in s.get('project_ids',[])):
        raise SafeError('Projects must be explicit stable IDs.')
    public_env=s.get('public_env',{})
    if not isinstance(public_env,dict):raise SafeError('Non-secret environment settings must be an object.')
    for key,value in public_env.items():
        if not ENV.fullmatch(key) or SENSITIVE.search(key) or key in RUNTIME_ENV or key in ('PYTHONPATH','PYTHONHOME','NODE_OPTIONS','LD_PRELOAD','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY') or not isinstance(value,str) or len(value)>1024:
            raise SafeError('Use only non-secret connector settings; execution and proxy overrides are not allowed.')
    if s.get('service')=='cloudflare':
        if not re.fullmatch(r'[0-9a-fA-F]{32}',s.get('account_id','')):raise SafeError('Cloudflare profiles require a 32-character account ID.')
        if public_env.get('CLOUDFLARE_ACCOUNT_ID',s['account_id'])!=s['account_id']:raise SafeError('Conflicting Cloudflare account bindings.')
    refs = s.get("credential_refs", [])
    if s.get('oauth'):
        if s['kind']!='http' or refs:raise SafeError('OAuth is supported for hosted MCP endpoints and cannot be mixed with API-key bindings.')
        settings=s['oauth']
        if not isinstance(settings.get('allowed_origins'),list) or not settings['allowed_origins']:raise SafeError('Review explicit OAuth authorization origins first.')
        for value in settings['allowed_origins']:
            validate_url(value,origin_only=True)
            if value.endswith('/'):raise SafeError('Use OAuth origins without a trailing slash.')
        if not isinstance(settings.get('callback_port',8770),int) or not 1024<=settings.get('callback_port',8770)<=65535:raise SafeError('Choose an unprivileged OAuth callback port.')
    if not isinstance(refs,list) or len(refs)>8:
        raise SafeError("Use at most eight explicit credential bindings.")
    bindings = set()
    for binding in refs:
        if set(binding) != {"kind", "name", "reference"} or binding["kind"] not in ("env", "header"):
            raise SafeError("Choose an environment/header binding with a credential reference.")
        name = binding["name"]
        if not isinstance(name,str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}",name):
            raise SafeError("Invalid credential binding name.")
        if name.upper() in RUNTIME_ENV or name.upper() in ("BWS_ACCESS_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS", "LD_PRELOAD", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "HOST", "COOKIE"):
            raise SafeError("This binding name is reserved and cannot be delivered to a connector.")
        key=(binding["kind"], name.lower())
        if key in bindings:raise SafeError("Duplicate credential binding.")
        bindings.add(key)
        validate_reference(binding["reference"])
    transport = s.get("transport", {})
    if s["kind"] in ("http", "portainer"):
        validate_url(s.get("url", ""),origin_only=s["kind"]=="portainer",private_http=s.get("private_network_http") is True)
    if s["kind"] == "portainer":
        if len(refs)!=1 or refs[0]["name"]!="PORTAINER_API_KEY" or refs[0]["kind"]!="env":
            raise SafeError("Portainer needs one PORTAINER_API_KEY credential reference.")
    elif s["kind"] == "sample":
        if refs:raise SafeError("The sample connector takes no credentials.")
    elif s["kind"] == "stdio":
        command=transport.get("command", "")
        if not Path(command).is_absolute() or Path(command).suffix.lower() in (".cmd", ".bat", ".ps1"):
            raise SafeError("Choose an absolute native executable; no shell shims.")
        if not transport.get("version") or not transport.get("package"):
            raise SafeError("Record the installed package and pinned version before testing.")
        if not isinstance(transport.get("args", []),list) or not all(isinstance(a,str) and len(a)<4096 for a in transport.get("args",[])):
            raise SafeError("Arguments must be an array of strings.")
        if any(a.startswith('-') and SENSITIVE.search(a.split('=')[0]) for a in transport.get('args',[])):
            raise SafeError('Credential command-line arguments are not accepted; use explicit environment references.')
        # Ordinary additions are declarative; env bindings cannot smuggle literal keys.
        if transport.get("env") or transport.get("headers"):
            raise SafeError("Use credential references; literal environment/header values are not accepted.")
        if any(r["kind"]!="env" for r in refs):raise SafeError("stdio servers accept environment bindings only.")
    elif any(r["kind"]!="header" for r in refs):
        raise SafeError("Hosted endpoints accept header bindings only.")
    if not isinstance(s.get("allowed_tools", []), list) or len(s.get("allowed_tools",[]))>100:
        raise SafeError("Choose an explicit tool allowlist, at most 100 tools.")
    if any(not isinstance(t,str) or not TOOL.fullmatch(t) for t in s.get("allowed_tools", [])):
        raise SafeError("Invalid tool name in policy.")
    if any(len(s['id']+'__'+t)>64 for t in s.get('allowed_tools',[])):
        raise SafeError('Choose a shorter profile ID so each published tool name fits the 64-character client limit.')
    if s["kind"]=="portainer" and set(s.get("allowed_tools",[]))-set(PORTAINER_TOOLS):
        raise SafeError("Portainer exposes only its implemented read-only tools.")
    if s.get("enabled") and (not s.get("allowed_tools") or not s.get("reviewed_read_only")):
        raise SafeError("Review the selected read-only operations before publishing.")
    for tool in s.get('tools',[]):
        validate_schema(tool.get('inputSchema',{}))
        if tool.get('outputSchema') is not None:validate_schema(tool['outputSchema'])
    if len(encode(s))>65536:
        raise SafeError("Service definition is too large.")


class Registry:
    def __init__(self, directory):
        self.dir=Path(directory).resolve()
        self.path=self.dir/'mcp-services.json'

    def load(self):
        raw=self.path.read_bytes() if self.path.exists() else encode({"schema_version":1,"services":[]})
        if len(raw)>2*1024*1024:raise SafeError("Managed catalogue exceeds size limit.")
        try:
            data=json.loads(raw)
            assert data['schema_version']==1 and isinstance(data['services'],list)
            ids=[s['id'] for s in data['services']]
            assert len(ids)==len(set(ids))
            for s in data['services']:validate_service(s)
        except (ValueError,KeyError,TypeError,AssertionError):
            raise SafeError("Managed catalogue is invalid; restore a known backup.") from None
        return data,digest(raw)

    def commit(self, data, expected):
        self.dir.mkdir(parents=True,exist_ok=True)
        with portalocker.Lock(str(self.dir/'mcp-services.lock'),timeout=3):
            _,current=self.load()
            if current!=expected:raise SafeError("Catalogue changed externally. Refresh and review again.")
            backup=self.dir/'mcp-backups'
            backup.mkdir(exist_ok=True)
            if self.path.exists():
                atomic(backup/f'{time.time_ns()}-{current[:12]}.json',self.path.read_bytes())
            atomic(self.path,encode(data))
        return self.load()[1]

    def save(self, service, expected):
        validate_service(service)
        data,_=self.load()
        old=next((s for s in data['services'] if s['id']==service['id']),{})
        # Preserve extension fields not touched by the editor.
        merged={**old,**copy.deepcopy(service)}
        validate_service(merged)
        data['services']=[s for s in data['services'] if s['id']!=service['id']]+[merged]
        return self.commit(data,expected)

    def remove(self, id, expected):
        data,_=self.load()
        data['services']=[s for s in data['services'] if s['id']!=id]
        return self.commit(data,expected)

    def backups(self):
        return sorted([p.name for p in (self.dir/'mcp-backups').glob('*.json')],reverse=True)[:50]

    def restore(self, name, expected):
        if name not in self.backups():raise SafeError("Choose a retained backup.")
        data=json.loads((self.dir/'mcp-backups'/name).read_bytes())
        for s in data['services']:validate_service(s)
        return self.commit(data,expected)

    def selected(self,id):
        data,_=self.load()
        for service in data['services']:
            if service['id']==id:return service
        raise SafeError("Service not found.")
