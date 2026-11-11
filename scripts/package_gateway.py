"""Local Windows host bundle; excludes data, credentials, caches and virtualenvs."""
from pathlib import Path
import hashlib
import json
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'runtime/mcp-gateway'


def package(helper=None,output=None,write_checksums=True):
    helper=Path(helper) if helper else ROOT/'dist/connections-manager/ecpa-connect_windows_amd64.exe'
    if not helper.is_file():raise SystemExit('Package connections-manager first to produce its matching helper.')
    diagnostic=json.loads(subprocess.check_output([str(helper),'diagnostics'],timeout=10,text=True))
    if diagnostic!={'name':'ecpa-connect','version':'0.8.0'}:raise SystemExit('Unexpected helper version.')
    output=Path(output) if output else ROOT/'dist/mcp-gateway';output.mkdir(parents=True,exist_ok=True)
    archive=output/'ecpa-mcp-gateway_0.2.0_windows_bundle.zip'
    files=[SOURCE/n for n in ('pyproject.toml','requirements-windows.lock','README.md','HOST-READINESS.md')]
    for directory,pattern in [('ecpa_gateway','*.py'),('windows','*.ps1'),('examples','*')]:
        files.extend(p for p in (SOURCE/directory).glob(pattern) if p.is_file())
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(files):z.write(path,path.relative_to(SOURCE).as_posix())
        z.write(helper,'ecpa-connect.exe')
        z.write(ROOT/'LICENSE','LICENSE')
    if write_checksums:(output/'checksums.txt').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
    print(archive)
    return archive


if __name__=='__main__':package()
