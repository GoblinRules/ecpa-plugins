"""Install checksum-pinned build toolchains locally; no system/PATH changes."""
import concurrent.futures
import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile
ROOT=Path(__file__).resolve().parents[1]/'test-artifacts/toolchains'
SOURCES=[('https://go.dev/dl/go1.27.3.windows-amd64.zip','f26081f438319757f8a1b46d7d0b2c5ec7583d4038e485e0aa725cfde7885fff','go/bin/go.exe'),('https://ziglang.org/download/0.14.1/zig-x86_64-windows-0.14.1.zip','554f5378228923ffd558eac35e21af020c73789d87afeabf4bfd16f2e6feed2c','zig-x86_64-windows-0.14.1/zig.exe')]
def install(source):
    url,digest,executable=source
    if (ROOT/executable).is_file():
        print('Using local toolchain:',executable)
        return
    blob=urllib.request.urlopen(url,timeout=120).read()
    if hashlib.sha256(blob).hexdigest()!=digest: raise RuntimeError('Toolchain checksum mismatch')
    ROOT.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for name in archive.namelist():
            if not (ROOT/name).resolve().is_relative_to(ROOT.resolve()): raise RuntimeError('Unsafe archive path')
        archive.extractall(ROOT)
    print('Verified official archive:',url)
if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(install,SOURCES))
