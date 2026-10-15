"""Compatibility entry point: build this plugin release from any directory."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[3]
subprocess.run([sys.executable, str(root / "scripts/package.py"), "--plugin", "agent-instructions"], cwd=root, check=True)
