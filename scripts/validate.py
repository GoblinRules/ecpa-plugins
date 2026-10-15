"""Validate the local plugin catalogue against the Rust workspace."""
import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]

def catalogue():
    registry = json.loads((ROOT / "registry.json").read_text(encoding="utf-8"))
    assert registry["schema_version"] == 1, "Unsupported registry schema"
    version = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))["workspace"]["package"]["version"]
    assert re.fullmatch(r"\d+(?:\.\d+)+", version), "Store requires a dotted numeric version"
    entries = registry["plugins"]
    assert entries, "Registry is empty"
    seen = set()
    for entry in entries:
        plugin_id = entry["id"]
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", plugin_id), "Invalid plugin ID"
        assert plugin_id not in seen, "Duplicate plugin ID"
        seen.add(plugin_id)
        for field in ["name", "description", "author"]:
            assert isinstance(entry.get(field), str) and entry[field].strip(), f"Missing {field}"
        assert entry["repository"] == "https://github.com/GoblinRules/ecpa-plugins", "External release repositories need a build adapter"
        directory = ROOT / "plugins" / plugin_id
        package = tomllib.loads((directory / "Cargo.toml").read_text(encoding="utf-8"))
        assert package["package"]["name"] == plugin_id
        assert package["package"]["version"] == {"workspace": True}, "Plugins must share the collection version"
        assert "cdylib" in package["lib"]["crate-type"]
        assert "name" not in package["lib"], "Use the default library name for packaging"
        assert (directory / "README.md").is_file(), "Missing plugin README"
    directories = {p.parent.name for p in (ROOT / "plugins").glob("*/Cargo.toml")}
    assert directories == seen, "Every plugin must have a registry entry"
    return version, entries

if __name__ == "__main__":
    version, entries = catalogue()
    print(f"Validated {len(entries)} plugin(s), collection v{version}")
