"""Validate independent plugin versions and their dedicated release repositories."""
import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]

def catalogue(root=ROOT):
    registry = json.loads((root / 'registry.json').read_text(encoding='utf-8'))
    assert registry['schema_version'] == 1, 'Unsupported registry schema'
    entries = registry['plugins']
    assert entries, 'Registry is empty'
    seen, repositories, result = set(), set(), []
    for entry in entries:
        plugin_id = entry['id']
        assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', plugin_id), 'Invalid plugin ID'
        assert plugin_id not in seen, 'Duplicate plugin ID'
        seen.add(plugin_id)
        for field in ['name', 'description', 'author']:
            assert isinstance(entry.get(field), str) and entry[field].strip(), f'Missing {field}'
        repository = entry['repository']
        assert repository == f'https://github.com/GoblinRules/ecpa-{plugin_id}', 'Unexpected release repository'
        assert repository not in repositories, 'Each plugin needs its own release repository'
        repositories.add(repository)
        directory = root / 'plugins' / plugin_id
        manifest = directory / 'plugin.toml'
        if manifest.exists():
            package = tomllib.loads(manifest.read_text(encoding='utf-8'))['plugin']
            assert package['id'] == plugin_id and package['language'] == 'go'
            assert (directory / 'go.mod').is_file() and (directory / 'LICENSE').is_file()
            language = 'go'
        else:
            cargo = tomllib.loads((directory / 'Cargo.toml').read_text(encoding='utf-8'))
            package = cargo['package']
            assert package['name'] == plugin_id
            assert 'cdylib' in cargo['lib']['crate-type']
            assert 'name' not in cargo['lib'], 'Use the default library name for packaging'
            language = 'rust'
        version = package['version']
        assert isinstance(version, str) and re.fullmatch(r'\d+\.\d+\.\d+', version), 'Each plugin needs an explicit numeric version'
        if language == 'go':
            runtime_versions = re.findall(r'\bpluginVersion\s*=\s*"([^"]+)"', '\n'.join(p.read_text(encoding='utf-8') for p in directory.glob('*.go') if not p.name.endswith('_test.go')))
            assert runtime_versions == [version], 'Go runtime and manifest versions must agree'
        assert package['repository'] == repository, 'Runtime and store repositories must agree'
        assert (directory / 'README.md').is_file(), 'Missing plugin README'
        result.append({**entry, 'version': version, 'language': language})
    directories = {p.parent.name for pattern in ['*/Cargo.toml', '*/plugin.toml'] for p in (root / 'plugins').glob(pattern)}
    assert directories == seen, 'Every plugin must have a registry entry'
    return result

def select_plugins(plugin=None):
    entries = catalogue()
    if plugin is None:
        return entries
    matches = [entry for entry in entries if entry['id'] == plugin]
    if not matches:
        raise ValueError(f'Unknown plugin: {plugin}')
    return matches

if __name__ == '__main__':
    entries = catalogue()
    for entry in entries:
        print(f"{entry['id']} v{entry['version']} -> {entry['repository']}")
    print(f'Validated {len(entries)} independently versioned plugins')
