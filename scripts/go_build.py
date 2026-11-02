"""Offline native Go plugin builds using an explicitly installed toolchain."""
import os
from pathlib import Path
import platform
import shutil
import subprocess
import struct
from validate import ROOT

def go_environment():
    local = ROOT / 'test-artifacts/toolchains'
    go = os.environ.get('ECPA_GO')
    if not go and (local / 'go/bin/go.exe').exists(): go = str(local / 'go/bin/go.exe')
    if not go: go = shutil.which('go')
    if not go: raise RuntimeError('Install Go 1.27.3 or set ECPA_GO; see docs/go-plugins.md')
    env = {**os.environ, 'GOTOOLCHAIN': 'local', 'CGO_ENABLED': '1', 'GOPROXY': 'off', 'GOSUMDB': 'off', 'GOFLAGS': ''}
    if platform.system() == 'Windows' and not env.get('CC'):
        zig = shutil.which('zig') or str(local / 'zig-x86_64-windows-0.14.1/zig.exe')
        if not Path(zig).is_file(): raise RuntimeError('Install Zig 0.14.1 or set CC; see docs/go-plugins.md')
        env['CC'] = '"'+zig+'" cc -target x86_64-windows-gnu'
    version = subprocess.check_output([go, 'version'], text=True, env=env)
    if ' go1.27.3 ' not in version: raise RuntimeError('Use the pinned Go 1.27.3 build toolchain')
    return go, env

def build_go(entry):
    if platform.system() != 'Windows' or platform.machine() not in ['AMD64','x86_64']:
        raise RuntimeError('These releases are currently validated for Windows amd64 only')
    go, env = go_environment()
    source = ROOT / 'plugins' / entry['id']
    output = ROOT / 'target/go' / (entry['id']+'.dll')
    output.parent.mkdir(parents=True, exist_ok=True)
    mode = 'vendor' if (source / 'vendor').exists() else 'readonly'
    subprocess.run([go, 'build', '-mod='+mode, '-trimpath', '-buildmode=c-shared', '-o', str(output), '.'], cwd=source, env=env, check=True)
    settings = subprocess.check_output([go, 'version', '-m', str(output)], text=True, env=env)
    if 'integration_fixture' in settings: raise RuntimeError('Refusing to package a fixture binary')
    data = output.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if data[pe:pe+4] != b'PE\0\0' or not struct.unpack_from('<H', data, pe+24+70)[0] & 0x40:
        raise RuntimeError('Release DLL must retain Windows ASLR')
    return output
