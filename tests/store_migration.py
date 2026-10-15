"""Verify historical DLLs upgrade through the real store without changing config.

Run after publishing all dedicated releases but before switching registry master.
Uses only a temporary core, copies of old release DLLs, and fixture files.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--core', required=True)
parser.add_argument('--registry', required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
entries = json.loads((root / 'registry.json').read_text())['plugins']
key = 'isolated-migration-test-key'

with tempfile.TemporaryDirectory(prefix='ecpa-store-migration-') as temp:
    home = Path(temp)
    binaries = home / 'plugins/windows/amd64'
    binaries.mkdir(parents=True)
    configs = {}
    for entry in entries:
        id = entry['id']
        archive = root / 'dist' / f'{id}_0.6.1_windows_amd64.zip'
        with zipfile.ZipFile(archive) as z:
            (binaries / f'{id}-v0.6.1.dll').write_bytes(z.read(f'{id}.dll'))
        configs[id] = {'enabled': True, 'migration-marker': 'preserve-me',
            'store': {'source-url': args.registry, 'version': '0.6.1',
                      'repository': 'https://github.com/GoblinRules/ecpa-plugins'}}
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}/v8/management'
    config = home / 'config.yaml'
    config.write_text(json.dumps({'host': '127.0.0.1', 'port': port,
        'auth-dir': str(home / 'auth'), 'api-keys': ['fixture-client-key'],
        'remote-management': {'secret-key': key, 'disable-control-panel': True},
        'plugins': {'enabled': True, 'dir': str(home / 'plugins'),
                    'store-sources': [args.registry], 'configs': configs}}))
    env = {**os.environ, 'AGENT_INSTRUCTIONS_HOME': str(home),
           'CLAUDE_CONFIG_DIR': str(home / '.claude'), 'CODEX_HOME': str(home / '.codex'),
           'KIMI_CODE_HOME': str(home / '.kimi-code')}

    def api(path, method='GET'):
        request = urllib.request.Request(base + path, method=method,
            headers={'Authorization': 'Bearer ' + key})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise AssertionError((path, error.code, error.read().decode())) from error

    def start(log):
        process = subprocess.Popen([args.core, '-config', str(config)], cwd=home,
            env=env, stdout=log, stderr=log)
        for _ in range(100):
            try:
                if len(api('/plugins')['plugins']) == len(entries):
                    return process
            except (OSError, AssertionError):
                pass
            if process.poll() is not None:
                raise RuntimeError('Fixture core exited')
            time.sleep(.1)
        process.terminate()
        process.wait(timeout=15)
        raise RuntimeError('Fixture core did not start')

    with (home / 'core.log').open('w') as log:
        process = start(log)
        try:
            installed = {p['id']: p for p in api('/plugins')['plugins']}
            assert all(installed[e['id']]['metadata']['version'] == '0.6.1' for e in entries)
            store = api('/plugins/store')
            listings = {p['id']: p for p in store['plugins'] if p['source_url'] == args.registry}
            assert len(listings) == len(entries), store.get('source_errors')
            for entry in entries:
                id = entry['id']
                listing = listings[id]
                expected = tomllib.loads((root / 'plugins' / id / 'Cargo.toml').read_text())['package']['version']
                assert listing['installed_version'] == '0.6.1', listing
                assert listing['version'] == expected and listing['update_available'], listing
                assert listing['repository'] == entry['repository'], listing
                result = api('/plugins/store/' + id + '/install?source=' + urllib.parse.quote(listing['source_id']), 'POST')
                assert result['version'] == expected, result
                saved = api('/config/plugins/configs/' + id)
                assert saved['migration-marker'] == 'preserve-me', saved
                print(f'UPGRADED {id}: 0.6.1 -> {expected}; config preserved', flush=True)
            process.terminate()
            process.wait(timeout=15)
            process = start(log)
            installed = {p['id']: p for p in api('/plugins')['plugins']}
            for entry in entries:
                package = tomllib.loads((root / 'plugins' / entry['id'] / 'Cargo.toml').read_text())['package']
                meta = installed[entry['id']]['metadata']
                assert meta['version'] == package['version'], meta
                assert meta['github_repository'] == entry['repository'], meta
            print('PASS: all seven store upgrades, preserved config, and restarted DLL metadata', flush=True)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
