"""Client-side key generation: transfer only a fingerprint to the central host."""
import json
import os
from pathlib import Path
import re
import secrets
import portalocker
from .registry import ID,atomic,encode
from .security import SafeError,validate_url,vault_put,auth_target,token_digest


def check_id(value):
    if not ID.fullmatch(value) or value=='admin':raise SafeError('Use a stable client ID other than admin.')


def client_init(path,url,identity):
    check_id(identity);validate_url(url)
    if not url.endswith('/mcp'):raise SafeError('Use the exact authenticated gateway /mcp URL.')
    path=Path(path).resolve()
    if path.exists():raise SafeError('Client configuration already exists; its key was preserved.')
    path.parent.mkdir(parents=True,exist_ok=True)
    value=secrets.token_urlsafe(48)
    if os.name=='nt':
        target=auth_target(path.parent,identity);vault_put(target,value);location={'vault_target':target}
    else:
        key=path.parent/(identity+'.secret');atomic(key,value.encode());key.chmod(0o600);location={'secret_file':str(key)}
    fingerprint=token_digest(value)
    atomic(path,encode({'schema_version':1,'url':url,'identities':{identity:{**location,'sha256':fingerprint}}}))
    return {'identity':identity,'sha256':fingerprint,'config':str(path),'next':'Register this public fingerprint and explicit profile/group/project grants on the central runtime. No service credentials or bearer key were exported.'}


def grant_client(path,identity,fingerprint,services,groups,projects):
    check_id(identity)
    if not re.fullmatch('[0-9a-f]{64}',fingerprint):raise SafeError('Supply the SHA-256 fingerprint produced by client-init.')
    if not services or any(not ID.fullmatch(x) for x in [*services,*groups,*projects]):raise SafeError('Select explicit stable profile, group and project IDs; wildcard grants are not accepted.')
    path=Path(path)
    with portalocker.Lock(str(path)+'.lock',timeout=3):
        cfg=json.loads(path.read_bytes())
        old=cfg['identities'].get(identity,{})
        if old.get('sha256') not in (None,fingerprint):raise SafeError('Identity already uses another key. Revoke it before replacing its fingerprint.')
        cfg['identities'][identity]={**old,'sha256':fingerprint,'services':services,'groups':groups,'project_ids':projects}
        atomic(path,encode(cfg))
    return {'granted':identity,'services':services,'groups':groups,'project_ids':projects}


def revoke_client(path,identity):
    check_id(identity);path=Path(path)
    with portalocker.Lock(str(path)+'.lock',timeout=3):
        cfg=json.loads(path.read_bytes());cfg['identities'].pop(identity,None);atomic(path,encode(cfg))
    return {'revoked':identity,'message':'New requests are denied immediately. Already-running calls may finish.'}
