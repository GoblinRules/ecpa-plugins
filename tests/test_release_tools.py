import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import validate
import package


class ReleaseToolsTest(unittest.TestCase):
    def test_connections_helper_is_separate_and_checksummed(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binaries = root / 'target/release'
            binaries.mkdir(parents=True)
            (binaries / 'connections_manager.dll').write_bytes(b'fixture DLL')
            (binaries / 'ecpa-connect.exe').write_bytes(b'fixture helper')
            entry = {'id': 'connections-manager', 'version': '0.1.0', 'repository': 'https://github.com/GoblinRules/ecpa-connections-manager'}
            with patch.object(package, 'ROOT', root), patch.object(package, 'select_plugins', return_value=[entry]), patch.object(package.platform, 'system', return_value='Windows'), patch.object(package.platform, 'machine', return_value='AMD64'), patch.object(package.subprocess, 'run'), patch.object(package.subprocess, 'check_output', return_value='a' * 40):
                _, assets = package.package('connections-manager')[0]
            with zipfile.ZipFile(assets[0]) as archive:
                self.assertEqual(archive.namelist(), ['connections-manager.dll'])
            self.assertEqual(assets[3].name, 'ecpa-connect_windows_amd64.exe')
            self.assertIn(hashlib.sha256(b'fixture helper').hexdigest(), assets[1].read_text())

    def test_versions_can_diverge_without_changing_other_plugins(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copy2(validate.ROOT / 'registry.json', root)
            for source in (validate.ROOT / 'plugins').iterdir():
                if not source.is_dir():
                    continue
                dest = root / 'plugins' / source.name
                dest.mkdir(parents=True)
                for name in ['Cargo.toml', 'README.md']:
                    shutil.copy2(source / name, dest)
            before = {e['id']: e['version'] for e in validate.catalogue(root)}
            manifest = root / 'plugins/mcp-manager/Cargo.toml'
            manifest.write_text(manifest.read_text().replace(f'version = "{before["mcp-manager"]}"', 'version = "1.2.3"'))
            after = {e['id']: e['version'] for e in validate.catalogue(root)}
            self.assertEqual(after.pop('mcp-manager'), '1.2.3')
            before.pop('mcp-manager')
            self.assertEqual(before, after)

    def test_unknown_plugin_is_rejected_before_build(self):
        with self.assertRaises(ValueError):
            validate.select_plugins('../not-a-plugin')

    def test_selected_package_uses_own_version_and_only_its_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / 'target/release/mcp_manager.dll'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'fixture DLL')
            entry = {'id': 'mcp-manager', 'version': '1.2.3', 'repository': 'https://github.com/GoblinRules/ecpa-mcp-manager'}
            with patch.object(package, 'ROOT', root), patch.object(package, 'select_plugins', return_value=[entry]), patch.object(package.platform, 'system', return_value='Windows'), patch.object(package.platform, 'machine', return_value='AMD64'), patch.object(package.subprocess, 'run') as run, patch.object(package.subprocess, 'check_output', return_value='a' * 40):
                _, assets = package.package('mcp-manager')[0]
            self.assertEqual(run.call_args.args[0], ['cargo', 'build', '--release', '--locked', '-p', 'mcp-manager'])
            self.assertEqual(assets[0].name, 'mcp-manager_1.2.3_windows_amd64.zip')
            with zipfile.ZipFile(assets[0]) as archive:
                self.assertEqual(archive.namelist(), ['mcp-manager.dll'])
                self.assertEqual(archive.read('mcp-manager.dll'), b'fixture DLL')
            self.assertEqual(json.loads(assets[2].read_text())['version'], '1.2.3')
            self.assertEqual([p.name for p in (root / 'dist').iterdir()], ['mcp-manager'])


if __name__ == '__main__':
    unittest.main()
