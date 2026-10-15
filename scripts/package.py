"""Build a store-compatible release archive for the current platform."""
import hashlib
import pathlib
import platform
import subprocess
import tomllib
import zipfile

root = pathlib.Path(__file__).resolve().parents[1]
subprocess.run(["cargo", "build", "--release", "--locked"], cwd=root, check=True)
version = tomllib.loads((root / "Cargo.toml").read_text())["package"]["version"]
os_name = {"Windows": "windows", "Linux": "linux", "Darwin": "darwin"}[platform.system()]
arch = {"AMD64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}[platform.machine()]
extension = {"windows": "dll", "linux": "so", "darwin": "dylib"}[os_name]
prefix = "" if os_name == "windows" else "lib"
binary = root / "target" / "release" / f"{prefix}agent_instructions.{extension}"
dist = root / "dist"
dist.mkdir(exist_ok=True)
archive = dist / f"agent-instructions_{version}_{os_name}_{arch}.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as out:
    out.write(binary, f"agent-instructions.{extension}")
checksums = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in sorted(dist.glob(f"agent-instructions_{version}_*.zip")))
(dist / "checksums.txt").write_text(checksums, encoding="utf-8")
print(archive)

