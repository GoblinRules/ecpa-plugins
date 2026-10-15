"""Publish one plugin to its dedicated repository using the current gh credentials."""
import argparse
import json
import subprocess
from pathlib import Path
import tempfile
from package import package
from validate import ROOT, select_plugins

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--plugin', required=True)
parser.add_argument('--repository', required=True, help='Expected owner/repository (guards the publish destination)')
parser.add_argument('--notes-file', type=Path)
args = parser.parse_args()
entry = select_plugins(args.plugin)[0]
assert entry['repository'] == 'https://github.com/'+args.repository, 'Publish destination differs from registry'
assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True).strip(), 'Commit tracked source changes before publishing'
tag = 'v'+entry['version']
# A missing release and a network/auth failure must not be confused.
releases = json.loads(subprocess.check_output(['gh', 'api', f'repos/{args.repository}/releases?per_page=100'], text=True))
assert not any(release['tag_name'] == tag for release in releases), 'Release already exists; never replace published artifacts'
_, assets = package(args.plugin)[0]
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
source = assets[0].parent / f"{args.plugin}_{entry['version']}_source.zip"
subprocess.run(['git', 'archive', '--format=zip', f'--output={source}', 'HEAD'], cwd=ROOT, check=True)
assets.append(source)
notes = args.notes_file.read_text(encoding='utf-8') if args.notes_file else entry['description']
notes += f'\n\nSource: https://github.com/GoblinRules/ecpa-plugins/tree/{commit}/plugins/{args.plugin}\n\nBuilt from `{commit}`. `release.json` records the source revision and binary checksum. The source archive includes the shared workspace needed to reproduce this plugin.\n'
with tempfile.TemporaryDirectory(prefix='ecpa-release-notes-') as temp:
    path = Path(temp) / 'notes.md'
    path.write_text(notes, encoding='utf-8')
    subprocess.run(['gh', 'release', 'create', tag, *map(str, assets), '--repo', args.repository,
        '--title', f"{entry['name']} {tag}", '--notes-file', str(path), '--latest'], check=True)
