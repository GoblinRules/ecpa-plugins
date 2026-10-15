"""Prepare documentation/workflow files for one dedicated release repository."""
import argparse
import json
from pathlib import Path
from validate import ROOT, select_plugins

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--plugin', required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
entry = select_plugins(args.plugin)[0]
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=True)
assert not any(output.iterdir()), 'Output must be empty; existing repository files are never overwritten'
repo = entry['repository']
source = f"https://github.com/GoblinRules/ecpa-plugins/tree/master/plugins/{args.plugin}"
readme = f'''# {entry['name']}

![Latest release]({repo}/releases/latest/badge.svg)

{entry['description']}

This is the dedicated **release repository** for `{args.plugin}`. It owns this plugin's releases and version history. The source lives in the shared [ECPA Plugins workspace]({source}); shared libraries are maintained once, rather than copied between seven repositories.

## Install and update

Add this public registry in ECPA's plugin settings:

```text
https://raw.githubusercontent.com/GoblinRules/ecpa-plugins/master/registry.json
```

Refresh the Plugin store and install **{entry['name']}**. Existing users keep the same registry URL and plugin ID. Restart the core when prompted. Windows x64 binaries are available under [Releases]({repo}/releases).

## Documentation

- [Usage, configuration and supported features]({source}/README.md)
- [Shared agent tools documentation](https://github.com/GoblinRules/ecpa-plugins/blob/master/docs/agent-tools.md)
- [Source workspace and contributing](https://github.com/GoblinRules/ecpa-plugins)
- [Release process](https://github.com/GoblinRules/ecpa-plugins/blob/master/docs/releases.md)

## Repository layout

```text
README.md                      Installation and source links
LICENSE                        MIT license
THIRD_PARTY_NOTICES.md          Agent icon attribution
plugin.json                    Plugin and source identity
.github/workflows/release.yml   Build and publish this plugin from a source commit
```

Each release includes the DLL ZIP, SHA-256 checksums, `release.json` with its source commit, and a complete source workspace ZIP. The source commit in the release is authoritative; documentation on master may describe later changes.

## Publishing

Bump only `plugins/{args.plugin}/Cargo.toml` in the source workspace, update its lockfile, test, commit and push. Run **Actions → Publish plugin release** here with the full 40-character source commit SHA. The workflow builds only this plugin and publishes its version using this repository's own GitHub Actions token. No cross-repository token or token for end users is required.

Versions through 0.6.1 were published in the old collection repository. 0.6.2 starts independent releases without downgrading installed plugins; future releases do not have to match other plugins.
'''
# GitHub's normal release badge endpoint, not a release asset.
readme = readme.replace(repo+'/releases/latest/badge.svg', 'https://img.shields.io/github/v/release/'+repo.removeprefix('https://github.com/'))
(output / 'README.md').write_text(readme, encoding='utf-8')
(output / 'LICENSE').write_bytes((ROOT / 'LICENSE').read_bytes())
(output / 'THIRD_PARTY_NOTICES.md').write_bytes((ROOT / 'assets/agents/THIRD_PARTY_NOTICES.md').read_bytes())
(output / 'plugin.json').write_text(json.dumps({'id': args.plugin, 'name': entry['name'], 'sourceRepository': 'https://github.com/GoblinRules/ecpa-plugins', 'sourcePath': 'plugins/'+args.plugin, 'registry': 'https://raw.githubusercontent.com/GoblinRules/ecpa-plugins/master/registry.json'}, indent=2)+'\n', encoding='utf-8')
workflow = output / '.github/workflows/release.yml'
workflow.parent.mkdir(parents=True)
workflow.write_text((ROOT / 'distribution/templates/release.yml').read_text().replace('__PLUGIN_ID__', args.plugin), encoding='utf-8')
print(output)
