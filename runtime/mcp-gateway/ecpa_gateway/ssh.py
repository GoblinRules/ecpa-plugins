"""Reuse SSH & Machines' verified catalogue through the single native helper."""
import json
import os
from pathlib import Path

from .security import SafeError, clean_env, bounded_process, redact


async def helper(service, config, action, extra=()):
    directory=Path(config.get('ssh_data_dir',str(Path(config['data_dir']).parent/'ssh-machines')))
    if not directory.is_absolute() or not (directory/'machines.json').is_file():
        raise SafeError('Configure and verify this machine in SSH & Machines first. Set its catalogue directory in runtime settings if needed.')
    environment=clean_env()
    for name in ('SSH_AUTH_SOCK','USERNAME','USERDOMAIN','COMSPEC','ALLUSERSPROFILE'):
        if name in os.environ:environment[name]=os.environ[name]
    try:
        raw=await bounded_process([config['helper_executable'],'--data-dir',str(directory),action,service['machine_id'],*extra],environment,timeout=25)
        return redact(json.loads(raw))
    except Exception:
        raise SafeError('SSH helper failed. Check helper version, key-owning runtime identity, machine revision and pinned host key. A timed-out operation may have started; verify before retrying.') from None


async def snapshot(service, config):
    data=await helper(service,config,'ssh-profile')
    if service.get('machine_revision') and data['revision']!=service['machine_revision']:
        raise SafeError('Saved SSH machine changed. Retest and review its gateway profile.')
    return data


async def operation(service, config, name):
    await snapshot(service,config)
    if name=='diagnostics':operation={'action':'diagnostics','service':''}
    else:
        operation=service.get('ssh_operations',{}).get(name)
        if not operation:raise SafeError('This machine operation is not assigned to the profile.')
    return await helper(service,config,'ssh-operation',(service['machine_revision'],operation['action'],operation['service']))
