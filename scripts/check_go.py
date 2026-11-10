"""Run format, race, and vet checks for both native Go plugins offline."""
import subprocess
import sys
import struct
import re
import shutil
from pathlib import Path
from go_build import go_environment
from validate import ROOT

go,env=go_environment()
# Go's Windows race runtime requires the Windows synchronization import library.
if sys.platform == 'win32':
    compiler_match = re.match(r'^"([^"]+)"|^(\S+)', env['CC'])
    compiler = Path(next(value for value in compiler_match.groups() if value))
    compiler = Path(shutil.which(str(compiler)) or compiler)
    if compiler.name.lower() in {'zig.exe', 'zig'}:
        # Hosted runners can discover MinGW's synchronization library while Zig
        # cannot link it by name. Build a deterministic import archive from the
        # pinned Zig distribution's Windows API definition instead of relying on
        # whichever SDK/MinGW installation happens to be on the runner.
        definition = compiler.parent/'lib/libc/mingw/lib-common/api-ms-win-core-synch-l1-2-0.def'
        imports = ROOT/'target/go-tests/imports'
        imports.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(compiler), 'dlltool', '-m', 'i386:x86-64',
            '-d', str(definition), '-l', str(imports/'libsynchronization.a')], check=True)
        env['CGO_LDFLAGS'] = '"-L'+imports.as_posix()+'" -lsynchronization'
    else:
        env['CGO_LDFLAGS'] = '-lapi-ms-win-core-synch-l1-2-0'
for plugin in ['claude-remote-login','zai-provider']:
    source=ROOT/'plugins'/plugin
    gofmt=Path(go).with_name('gofmt.exe')
    unformatted=subprocess.check_output([str(gofmt),'-l',*map(str,source.glob('*.go'))],text=True)
    if unformatted.strip(): raise RuntimeError('Unformatted Go files: '+unformatted)
    mode='-mod=vendor' if (source/'vendor').exists() else '-mod=readonly'
    if sys.platform == 'win32':
        # Go's race runtime requires a non-ASLR executable (Go issue #53539).
        # Zig 0.14 lacks the GNU flags Go uses to request this. Apply the same
        # PE flag change to the TEST executable only; release DLLs retain ASLR.
        binary = ROOT/'target/go-tests'/(plugin+'.test.exe')
        binary.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([go,'test','-c','-race',mode,'-o',str(binary),'.'],cwd=source,env=env,check=True)
        data = bytearray(binary.read_bytes())
        pe = struct.unpack_from('<I',data,0x3c)[0]
        assert data[pe:pe+4] == b'PE\0\0' and struct.unpack_from('<H',data,pe+24)[0] == 0x20b
        offset = pe+24+70
        flags = struct.unpack_from('<H',data,offset)[0]
        struct.pack_into('<H',data,offset,flags & ~0x60)
        binary.write_bytes(data)
        subprocess.run([str(binary),'-test.timeout=120s'],cwd=source,env=env,check=True)
    else:
        subprocess.run([go,'test','-race',mode,'./...'],cwd=source,env=env,check=True)
    subprocess.run([go,'vet',mode,'./...'],cwd=source,env=env,check=True)
