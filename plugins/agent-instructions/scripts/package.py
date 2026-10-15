"""Compatibility entry point: build the collection release from any directory."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[3]
subprocess.run([sys.executable, str(root / "scripts/package.py")], cwd=root, check=True)
