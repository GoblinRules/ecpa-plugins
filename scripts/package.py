"""Package all registered workspace plugins for the native platform."""
import hashlib
import platform
import subprocess
import zipfile
from validate import ROOT, catalogue

version, entries = catalogue()
subprocess.run(["cargo", "build", "--workspace", "--release", "--locked"], cwd=ROOT, check=True)
os_name = {"Windows": "windows", "Linux": "linux", "Darwin": "darwin"}[platform.system()]
arch = {"AMD64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}[platform.machine()]
extension = {"windows": "dll", "linux": "so", "darwin": "dylib"}[os_name]
prefix = "" if os_name == "windows" else "lib"
dist = ROOT / "dist"
dist.mkdir(exist_ok=True)
checksums = []
for entry in entries:
    plugin_id = entry["id"]
    binary = ROOT / "target" / "release" / f"{prefix}{plugin_id.replace('-', '_')}.{extension}"
    archive = dist / f"{plugin_id}_{version}_{os_name}_{arch}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
        out.write(binary, f"{plugin_id}.{extension}")
    checksums.append(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n")
    print(archive)
(dist / "checksums.txt").write_text("".join(checksums), encoding="utf-8")
