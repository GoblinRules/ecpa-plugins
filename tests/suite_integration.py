"""Exercise all suite DLLs in an isolated real core; --serve keeps the UI fixture open."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import tomllib
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--core', required=True)
parser.add_argument('--serve', action='store_true')
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[1]
KEY = 'isolated-plugin-test-key'
IDS = ['agent-profiles', 'mcp-manager', 'agent-diagnostics', 'prompt-library', 'config-snapshots', 'agent-skills']
with tempfile.TemporaryDirectory(prefix='ecpa-suite-test-') as folder:
    home = Path(folder)
    plugins = home / 'plugins'
    plugins.mkdir()
    for id in IDS:
        shutil.copy2(ROOT / 'target/release' / (id.replace('-', '_') + '.dll'), plugins / (id + '.dll'))
    (home / '.claude').mkdir()
    (home / '.codex').mkdir()
    (home / '.claude/CLAUDE.md').write_text('Original Claude\n', encoding='utf-8')
    (home / '.codex/AGENTS.md').write_text('Original Codex\n', encoding='utf-8')
    (home / '.claude.json').write_text('{"other":{"keep":true},"mcpServers":{}}', encoding='utf-8')
    (home / '.codex/config.toml').write_text('# keep this comment\nmodel = "fixture"\n', encoding='utf-8')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    config = home / 'config.yaml'
    config.write_text(json.dumps({'host': '127.0.0.1', 'port': port, 'auth-dir': str(home / 'auth'),
        'api-keys': ['fixture-client-key'], 'remote-management': {'allow-remote': False, 'secret-key': KEY, 'disable-control-panel': True},
        'plugins': {'enabled': True, 'dir': str(plugins), 'configs': {id: {'enabled': True} for id in IDS}}}), encoding='utf-8')
    env = {**os.environ, 'AGENT_INSTRUCTIONS_HOME': str(home), 'CLAUDE_CONFIG_DIR': str(home / '.claude'),
        'CODEX_HOME': str(home / '.codex'), 'KIMI_CODE_HOME': str(home / '.kimi-code')}
    base = f'http://127.0.0.1:{port}'

    def request(path, method='GET', data=None, auth=True):
        headers = {'Authorization': 'Bearer ' + KEY} if auth else {}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(base + path, method=method, headers=headers,
            data=json.dumps(data).encode() if data is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def api(id, endpoint='state', method='GET', data=None, status=200):
        code, raw = request(f'/v0/management/{id}/{endpoint}', method, data)
        assert code == status, (id, endpoint, code, raw)
        return json.loads(raw)

    def apply(id, preview):
        result = api(id, 'apply', 'POST', {'token': preview['token']})
        assert result['status'] == 'applied', result

    with (home / 'core.log').open('wb') as log:
        process = subprocess.Popen([str(Path(args.core).resolve()), '-config', str(config), '--local-model'],
            cwd=home, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            for _ in range(120):
                if process.poll() is not None:
                    raise RuntimeError((home / 'core.log').read_text(errors='replace'))
                try:
                    if all(request(f'/v0/management/{id}/state')[0] == 200 for id in IDS):
                        break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError((home / 'core.log').read_text(errors='replace'))
            code, raw = request('/v0/management/plugins')
            assert code == 200
            installed = {entry['id']: entry for entry in json.loads(raw)['plugins']}
            for id in IDS:
                package = tomllib.loads((ROOT / 'plugins' / id / 'Cargo.toml').read_text())['package']
                assert installed[id]['metadata']['version'] == package['version'], installed[id]
                assert installed[id]['metadata']['github_repository'] == package['repository'], installed[id]
            for id in IDS:
                assert request(f'/v0/management/{id}/state', auth=False)[0] == 401
                api(id)  # Successful authentication resets the core's failed-attempt counter.
                code, page = request(f'/v0/resource/plugins/{id}/editor', auth=False)
                assert code == 200 and b'<!doctype html>' in page and b'Original Claude' not in page
                assert request(f'/v0/resource/plugins/{id}/state', auth=False)[0] == 404

            # Profiles: persist a set, refuse a stale batch before the first write, apply once.
            id = 'agent-profiles'
            state = api(id)
            library = api(id, 'record', 'POST', {'id': 'work', 'name': 'Work', 'tags': ['coding'],
                'version': state['library']['version'], 'files': {'claude': 'Work Claude\n', 'codex': 'Work Codex\n'}})
            body = {'id': 'work', 'libraryVersion': library['version'], 'selected': ['claude', 'codex']}
            preview = api(id, 'preview', 'POST', body)
            (home / '.codex/AGENTS.md').write_text('External', encoding='utf-8')
            api(id, 'apply', 'POST', {'token': preview['token']}, 409)
            assert (home / '.claude/CLAUDE.md').read_text() == 'Original Claude\n'
            preview = api(id, 'preview', 'POST', body)
            apply(id, preview)
            api(id, 'apply', 'POST', {'token': preview['token']}, 400)
            assert (home / '.codex/AGENTS.md').read_text() == 'Work Codex\n'

            # MCP: only replace the server mapping; restore uses a reviewed full-file backup.
            for file_id, relative in [('claude-config', '.claude.json'), ('codex-config', '.codex/config.toml')]:
                before = (home / relative).read_bytes()
                f = next(f for f in api('mcp-manager')['files'] if f['id'] == file_id)
                server = {'docs': {'url': 'https://example.test/mcp', **({'type': 'http'} if file_id == 'claude-config' else {})}}
                preview = api('mcp-manager', 'preview', 'POST', {'id': file_id, 'version': f['version'], 'content': json.dumps(server)})
                assert (home / relative).read_bytes() == before
                apply('mcp-manager', preview)
                content = (home / relative).read_text()
                assert ('"keep": true' in content if file_id == 'claude-config' else '# keep this comment' in content)
                f = next(f for f in api('mcp-manager')['files'] if f['id'] == file_id)
                backup = api('mcp-manager', 'backups?id=' + file_id)['backups'][0]['name']
                preview = api('mcp-manager', 'restore-preview', 'POST', {'id': file_id, 'version': f['version'], 'backup': backup})
                apply('mcp-manager', preview)
                assert (home / relative).read_bytes() == before

            # Diagnostics never sends file contents or permits write routes.
            diagnostics = api('agent-diagnostics')
            assert len(diagnostics['files']) == 10
            assert all('content' not in f for f in diagnostics['files'])
            assert request('/v0/management/agent-diagnostics/apply', 'POST', {'token': 'invalid'})[0] == 404

            # Prompt library CRUD and stale catalog conflict.
            state = api('prompt-library')
            record = {'id': 'review', 'name': 'Code review', 'tags': ['coding'], 'version': state['library']['version'], 'content': '<literal> & review carefully'}
            library = api('prompt-library', 'record', 'POST', record)
            api('prompt-library', 'record', 'POST', record, 409)
            assert library['records'][0]['files']['prompt'] == record['content']
            api('prompt-library', 'record', 'DELETE', {'id': 'review', 'version': library['version']})

            # Snapshots restore only selected targets, leaving other files as-is.
            state = api('config-snapshots')
            saved_files = {f['id']: f['content'] for f in state['files'] if f['id'] in ['claude', 'codex-config']}
            library = api('config-snapshots', 'record', 'POST', {'id': 'baseline', 'name': 'Baseline', 'tags': [], 'version': state['library']['version'], 'files': saved_files})
            (home / '.claude/CLAUDE.md').write_text('Changed', encoding='utf-8')
            (home / '.codex/config.toml').write_text('model = "new"\n', encoding='utf-8')
            apply('config-snapshots', api('config-snapshots', 'preview', 'POST', {'id': 'baseline', 'libraryVersion': library['version'], 'selected': ['claude']}))
            assert (home / '.claude/CLAUDE.md').read_bytes().decode() == saved_files['claude']
            assert (home / '.codex/config.toml').read_text() == 'model = "new"\n'

            # New skills validate metadata and cannot escape a configured root.
            content = '---\nname: review\ndescription: Review code changes\n---\n\nRead the diff carefully.\n'
            api('agent-skills', 'preview', 'POST', {'id': 'codex/../escape', 'version': None, 'content': content}, 400)
            api('agent-skills', 'preview', 'POST', {'id': 'codex/review', 'version': None, 'content': 'bad'}, 400)
            apply('agent-skills', api('agent-skills', 'preview', 'POST', {'id': 'codex/review', 'version': None, 'content': content}))
            assert (home / '.agents/skills/review/SKILL.md').read_text() == content
            assert api('agent-skills')['files'][0]['content'] == content
            if not args.serve:
                # Exercise the host's actual quiesce/shutdown/unload path, not
                # just process termination. Other loaded plugins must survive.
                code, raw = request('/v0/management/plugins/prompt-library', 'DELETE')
                assert code == 200, (code, raw)
                assert not (plugins / 'prompt-library.dll').exists()
                assert request('/v0/management/prompt-library/state')[0] == 404
                assert api('agent-skills')['files'][0]['content'] == content
                print('PASS: targeted plugin unload leaves other plugins running', flush=True)
            print('PASS: six DLLs, authentication, profiles, batch conflicts, MCP preservation and restore, diagnostics, prompts, selective snapshots, skills', flush=True)
            if args.serve:
                print('PREVIEW_BASE=' + base, flush=True)
                print('FIXTURE_HOME=' + str(home), flush=True)
                print('TEST_KEY=' + KEY, flush=True)
                process.wait()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
