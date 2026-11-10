"""Explicit client reconciliation: narrow edits, previews, CAS checks and rollback."""
import copy
import json
import os
import sys
import time
from pathlib import Path
import tomlkit
import portalocker
from .registry import atomic, digest, encode
from .security import SafeError, redact, SENSITIVE, TOKEN_LITERAL

SERVER_NAME='ecpa-central'


def read(path):
    p=Path(path)
    if p.is_symlink():raise SafeError('Linked configuration files are not edited.')
    raw=p.read_bytes() if p.exists() else b''
    if len(raw)>4*1024*1024:raise SafeError('Client configuration exceeds size limit.')
    return raw


def parse(kind,raw):
    try:
        if kind=='codex':return tomlkit.parse(raw.decode('utf-8-sig'))
        return json.loads(raw.decode('utf-8-sig')) if raw else ([] if kind=='native' else {})
    except Exception:raise SafeError('Client configuration cannot be parsed; it was not changed.') from None


def definition(config_path,identity):
    return {'command':sys.executable,'args':['-m','ecpa_gateway.cli','--config',str(Path(config_path).resolve()),'bridge','--identity',identity]}


def preview(config_path, config, targets, removals=None):
    plans=[]
    removals=removals or {}
    if not isinstance(targets,list) or not targets or len(set(targets))!=len(targets):raise SafeError('Choose distinct client destinations.')
    for kind in targets:
        if kind not in ('codex','claude','native') or not config.get('client_paths',{}).get(kind):
            raise SafeError('Configure this destination path in runtime settings first.')
        path=Path(config['client_paths'][kind]).resolve()
        raw=read(path)
        data=parse(kind,raw)
        entry=definition(config_path,'claude' if kind=='claude' else 'codex')
        remove=removals.get(kind,[])
        if not isinstance(remove,list) or any(not isinstance(x,str) for x in remove):raise SafeError('Invalid replacement selection.')
        if kind=='native':
            if not isinstance(data,list) or any(not isinstance(s,dict) for s in data):raise SafeError('Native catalogue has an unsupported format.')
            existing=next((s for s in data if s.get('id')==SERVER_NAME),{})
            if existing and any(existing.get(k)!=v for k,v in entry.items()) and SERVER_NAME not in remove:
                raise SafeError('An ecpa-central entry already exists; explicitly select it for replacement.')
            updated={**existing,'id':SERVER_NAME,'name':'ECPA managed gateway','transport':'stdio',**entry,'env':{},'headers':{},'url':None,'enabled':True,'description':'Managed in Connections Manager → MCP services. One gateway entry for all approved services.'}
            data=[s for s in data if s.get('id')!=SERVER_NAME and s.get('id') not in remove]+[updated]
            after=encode(data)
        else:
            if not isinstance(data,dict):raise SafeError('Client configuration has an unsupported format.')
            key='mcp_servers' if kind=='codex' else 'mcpServers'
            mapping=data.setdefault(key,tomlkit.table() if kind=='codex' else {})
            if not isinstance(mapping,dict):raise SafeError('Client server map has an unsupported format.')
            if SERVER_NAME in mapping and dict(mapping[SERVER_NAME])!=entry and SERVER_NAME not in remove:
                raise SafeError('An ecpa-central entry already exists; explicitly select it for replacement.')
            for name in remove:mapping.pop(name,None)
            mapping[SERVER_NAME]=entry
            after=tomlkit.dumps(data).encode() if kind=='codex' else encode(data)
        plans.append({'kind':kind,'path':str(path),'before_hash':digest(raw),'after_hash':digest(after),
                      'remove':remove,'entry':entry,'before':raw,'after':after,'existed':path.exists()})
    return plans


def display(plans):
    return [{k:v for k,v in p.items() if k not in ('before','after')} for p in plans]


def apply(directory,plans):
    directory=Path(directory)
    with portalocker.Lock(str(directory/'client-config.lock'),timeout=3):
        for p in plans:
            if digest(read(p['path']))!=p['before_hash']:raise SafeError('Client configuration changed since preview; review again.')
        tx=str(time.time_ns())
        backup=directory/'client-backups'/tx
        backup.mkdir(parents=True)
        completed=[]
        try:
            for p in plans:
                if digest(read(p['path']))!=p['before_hash']:raise SafeError('Client configuration changed during apply.')
                atomic(backup/(p['kind']+'.before'),p['before'])
                atomic(p['path'],p['after'])
                completed.append(p)
            atomic(backup/'transaction.json',encode(display(plans)))
        except Exception:
            for p in reversed(completed):
                if digest(read(p['path']))==p['after_hash']:
                    if p['existed']:atomic(p['path'],p['before'])
                    else:Path(p['path']).unlink()
            raise SafeError('Client update failed; unchanged destinations were rolled back. Review files before retrying.') from None
        return tx


def rollback(directory,tx):
    if not isinstance(tx,str) or not tx.isdigit():raise SafeError('Invalid rollback transaction.')
    directory=Path(directory)
    backup=directory/'client-backups'/tx
    with portalocker.Lock(str(directory/'client-config.lock'),timeout=3):
        plans=json.loads((backup/'transaction.json').read_bytes())
        for p in plans:
            if digest(read(p['path']))!=p['after_hash']:raise SafeError('Client changed after setup; automatic rollback refused.')
        for p in plans:
            if p['existed']:atomic(p['path'],(backup/(p['kind']+'.before')).read_bytes())
            else:Path(p['path']).unlink()
    return {'rolled_back':tx}


def inventory(config):
    result=[]
    for kind,path in config.get('client_paths',{}).items():
        if kind not in ('codex','claude','native'):continue
        try:
            data=parse(kind,read(path))
            servers=data if kind=='native' else [{'id':name,**dict(v)} for name,v in data.get('mcp_servers' if kind=='codex' else 'mcpServers',{}).items()]
            for entry in servers:
                # Show identities and reasons, never raw command arguments/headers.
                blocked=bool(entry.get('env') or entry.get('headers') or entry.get('http_headers') or entry.get('bearer_token_env_var'))
                result.append({'source':kind,'id':entry.get('id'), 'name':entry.get('name',entry.get('id')),
                    'transport':'stdio' if entry.get('command') else 'http', 'has_literal_or_external_credentials':blocked,
                    'gateway':entry.get('id')==SERVER_NAME})
        except Exception:
            result.append({'source':kind,'error':'Cannot inspect this configuration; no changes made.'})
    return result


def import_candidate(config,source,id):
    if source not in ('claude','codex','native') or source not in config.get('client_paths',{}):raise SafeError('Unknown import source.')
    data=parse(source,read(config['client_paths'][source]))
    entries=data if source=='native' else [{'id':k,**dict(v)} for k,v in data.get('mcp_servers' if source=='codex' else 'mcpServers',{}).items()]
    entry=next((e for e in entries if e.get('id')==id),None)
    if not entry or id==SERVER_NAME:raise SafeError('Select an upstream service, not the gateway itself.')
    known={'id','name','command','args','env','url','headers','http_headers','type','transport','enabled','description'}
    if set(entry)-known:raise SafeError('Client-specific fields cannot be translated automatically. Review the original definition; nothing was imported.')
    if entry.get('env') or entry.get('headers') or entry.get('http_headers'):
        raise SafeError('This entry contains literal environment/header values. Add credential references in a new draft; literals were not copied.')
    if any(SENSITIVE.search(str(a)) or TOKEN_LITERAL.search(str(a)) for a in entry.get('args',[])):
        raise SafeError('Arguments may contain credentials. Review them locally before import.')
    if entry.get('type') in ('sse','websocket') or entry.get('transport')=='sse':raise SafeError('Legacy SSE/WebSocket import is not supported; use a Streamable HTTP endpoint.')
    draft={'id':id,'name':entry.get('name',id),'kind':'stdio' if entry.get('command') else 'http',
           'enabled':False,'allowed_tools':[],'credential_refs':[],'imported_from':{'source':source,'id':id}}
    if draft['kind']=='stdio':draft['transport']={'command':entry['command'],'args':entry.get('args',[]),'package':'review-required','version':'review-required'}
    else:draft['url']=entry.get('url','')
    return draft
