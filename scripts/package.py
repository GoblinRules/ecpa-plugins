"""Build all plugins, or --plugin ID, into separate per-plugin artifact folders."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import zipfile
from validate import ROOT, select_plugins
from go_build import build_go

def package(plugin=None):
    entries = select_plugins(plugin)
    rust_entries = [entry for entry in entries if entry.get('language', 'rust') == 'rust']
    if rust_entries:
        command = ['cargo', 'build', '--release', '--locked']
        command += ['-p', plugin] if plugin else ['--workspace']
        subprocess.run(command, cwd=ROOT, check=True)
    go_binaries = {entry['id']: build_go(entry) for entry in entries if entry.get('language') == 'go'}
    # Build the CLI without its own payload first, then embed that exact executable
    # in the library. The ZIP stays DLL-only for existing ECPA installers.
    if any(entry['id'] == 'connections-manager' for entry in entries):
        assert platform.system() == 'Windows', 'Connections Manager requires Windows Credential Manager'
        helper = ROOT / 'target/release/ecpa-connect.exe'
        entry = next(entry for entry in entries if entry['id'] == 'connections-manager')
        diagnostic = json.loads(subprocess.check_output([str(helper), 'diagnostics'], text=True, timeout=10))
        assert diagnostic == {'name': 'ecpa-connect', 'version': entry['version']}, 'Helper version mismatch'
        subprocess.run(['cargo', 'build', '--release', '--locked', '-p', 'connections-manager',
            '--lib', '--features', 'bundled-helper'], cwd=ROOT, check=True,
            env={**os.environ, 'ECPA_HELPER_BINARY': str(helper.resolve())})
    os_name = {'Windows': 'windows', 'Linux': 'linux', 'Darwin': 'darwin'}[platform.system()]
    arch = {'AMD64': 'amd64', 'x86_64': 'amd64', 'arm64': 'arm64', 'aarch64': 'arm64'}[platform.machine()]
    extension = {'windows': 'dll', 'linux': 'so', 'darwin': 'dylib'}[os_name]
    prefix = '' if os_name == 'windows' else 'lib'
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    outputs = []
    for entry in entries:
        plugin_id, version = entry['id'], entry['version']
        binary = go_binaries.get(plugin_id) or ROOT / 'target/release' / f"{prefix}{plugin_id.replace('-', '_')}.{extension}"
        dist = ROOT / 'dist' / plugin_id
        dist.mkdir(parents=True, exist_ok=True)
        archive = dist / f'{plugin_id}_{version}_{os_name}_{arch}.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as out:
            out.write(binary, f'{plugin_id}.{extension}')
            if entry.get('language') == 'go':
                for name in ['LICENSE', 'UPSTREAM-LICENSE', 'UPSTREAM.md', 'SECURITY.md', 'THIRD_PARTY_NOTICES.md']:
                    notice = ROOT / 'plugins' / plugin_id / name
                    if notice.exists(): out.write(notice, name)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        checksums = dist / 'checksums.txt'
        checksum_lines = [f'{digest}  {archive.name}\n']
        extra_assets = []
        if plugin_id == 'connections-manager':
            assert os_name == 'windows', 'Connections Manager requires Windows Credential Manager'
            helper = dist / f'ecpa-connect_{os_name}_{arch}.exe'
            shutil.copy2(ROOT / 'target/release/ecpa-connect.exe', helper)
            checksum_lines.append(f'{hashlib.sha256(helper.read_bytes()).hexdigest()}  {helper.name}\n')
            extra_assets.append(helper)
        checksums.write_text(''.join(checksum_lines), encoding='utf-8')
        manifest = dist / 'release.json'
        manifest.write_text(json.dumps({'plugin': plugin_id, 'version': version,
            'repository': entry['repository'], 'sourceRepository': 'https://github.com/GoblinRules/ecpa-plugins',
            'sourceCommit': commit, 'asset': archive.name, 'sha256': digest}, indent=2)+'\n', encoding='utf-8')
        outputs.append((entry, [archive, checksums, manifest, *extra_assets]))
        print(archive)
    return outputs

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin', help='Build only this plugin (default: all)')
    package(parser.parse_args().plugin)
