"""Opt-in clean install from the delivery ZIP, using only temporary vault keys."""
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
import pytest
from ecpa_gateway.security import auth_target


@pytest.mark.skipif(os.name!='nt' or os.environ.get('ECPA_TEST_INSTALLER')!='1',reason='Opt-in dependency installation from local bundle')
def test_clean_windows_bundle_install(tmp_path):
    import win32cred
    root=Path(__file__).resolve().parents[3]
    archive=root/'dist/connections-manager/ecpa-mcp-gateway_0.2.0_windows_bundle.zip'
    source=tmp_path/'source';destination=tmp_path/'installed'
    with zipfile.ZipFile(archive) as z:
        assert all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in z.namelist())
        assert not any('.venv' in n or n.endswith('.secret') for n in z.namelist())
        z.extractall(source)
    try:
        shell=Path(os.environ['SYSTEMROOT'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        result=subprocess.run([str(shell),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(source/'windows/Install-Runtime.ps1'),
            '-Python',sys._base_executable,'-Destination',str(destination),'-Helper',str(source/'ecpa-connect.exe'),
            '-Bws',sys._base_executable,'-HostId','installer-fixture'],capture_output=True,text=True,timeout=180)
        assert result.returncode==0,result.stdout[-1200:]+result.stderr[-1200:]
        cfg=json.loads((destination/'data/gateway-runtime.json').read_bytes())
        assert cfg['host_id']=='installer-fixture'
        assert all(not item['services'] for item in cfg['identities'].values())
        assert (destination/'venv/Scripts/python.exe').is_file()
    finally:
        for name in ('admin','codex','claude'):
            try:win32cred.CredDelete(auth_target(destination/'data',name),1,0)
            except Exception:pass
