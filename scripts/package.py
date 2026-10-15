"""Build all plugins, or --plugin ID, into separate per-plugin artifact folders."""
import argparse
import hashlib
import json
import platform
import subprocess
import zipfile
from validate import ROOT, select_plugins

def package(plugin=None):
    entries = select_plugins(plugin)
    command = ['cargo', 'build', '--release', '--locked']
    command += ['-p', plugin] if plugin else ['--workspace']
    subprocess.run(command, cwd=ROOT, check=True)
    os_name = {'Windows': 'windows', 'Linux': 'linux', 'Darwin': 'darwin'}[platform.system()]
    arch = {'AMD64': 'amd64', 'x86_64': 'amd64', 'arm64': 'arm64', 'aarch64': 'arm64'}[platform.machine()]
    extension = {'windows': 'dll', 'linux': 'so', 'darwin': 'dylib'}[os_name]
    prefix = '' if os_name == 'windows' else 'lib'
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    outputs = []
    for entry in entries:
        plugin_id, version = entry['id'], entry['version']
        binary = ROOT / 'target/release' / f"{prefix}{plugin_id.replace('-', '_')}.{extension}"
        dist = ROOT / 'dist' / plugin_id
        dist.mkdir(parents=True, exist_ok=True)
        archive = dist / f'{plugin_id}_{version}_{os_name}_{arch}.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as out:
            out.write(binary, f'{plugin_id}.{extension}')
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        checksums = dist / 'checksums.txt'
        checksums.write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
        manifest = dist / 'release.json'
        manifest.write_text(json.dumps({'plugin': plugin_id, 'version': version,
            'repository': entry['repository'], 'sourceRepository': 'https://github.com/GoblinRules/ecpa-plugins',
            'sourceCommit': commit, 'asset': archive.name, 'sha256': digest}, indent=2)+'\n', encoding='utf-8')
        outputs.append((entry, [archive, checksums, manifest]))
        print(archive)
    return outputs

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin', help='Build only this plugin (default: all)')
    package(parser.parse_args().plugin)
