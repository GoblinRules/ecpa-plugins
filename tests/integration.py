"""Run the built DLL against a real core, using isolated agent homes only.

python tests/integration.py --core C:/path/cli-proxy-api.exe
Add --serve to keep the fixture running for manual/browser UI verification.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--core", required=True)
parser.add_argument("--serve", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
KEY = "isolated-plugin-test-key"
API = "/v0/management/agent-instructions"

with tempfile.TemporaryDirectory(prefix="agent-instructions-test-") as temp:
    temp = Path(temp)
    plugins = temp / "plugins"
    plugins.mkdir()
    shutil.copy2(root / "target/release/agent_instructions.dll", plugins / "agent-instructions.dll")
    claude, codex = temp / "claude", temp / "codex"
    claude.mkdir()
    codex.mkdir()
    (claude / "CLAUDE.md").write_bytes(b"# Working agreements\r\n\r\n- Explain changes clearly.\r\n- Preserve <example> & code.\r\n")
    (codex / "AGENTS.md").write_text("# Codex defaults\n\n- Run relevant tests.\n", encoding="utf-8")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    config = temp / "config.yaml"
    # JSON is valid YAML and avoids Windows path escaping mistakes.
    config.write_text(json.dumps({"host": "127.0.0.1", "port": port,
        "auth-dir": str(temp / "auth"), "api-keys": ["fixture-client-key"],
        "remote-management": {"allow-remote": False, "secret-key": KEY, "disable-control-panel": True},
        "plugins": {"enabled": True, "dir": str(plugins), "configs": {"agent-instructions": {"enabled": True}}}}), encoding="utf-8")
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(claude), "CODEX_HOME": str(codex), "KIMI_CODE_HOME": str(temp / "kimi-code"), "AGENT_INSTRUCTIONS_HOME": str(temp)}
    base = f"http://127.0.0.1:{port}"

    def request(path, method="GET", data=None, authenticated=True):
        headers = {"Authorization": "Bearer " + KEY} if authenticated else {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(base + path, method=method, headers=headers,
            data=json.dumps(data).encode() if data is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def api(path, method="GET", data=None, status=200):
        code, raw = request(API + path, method, data)
        assert code == status, (path, code, raw)
        return json.loads(raw)

    with (temp / "core.log").open("wb") as log:
        process = subprocess.Popen([str(Path(args.core).resolve()), "-config", str(config), "--local-model"],
            cwd=temp, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            for attempt in range(100):
                if process.poll() is not None:
                    raise RuntimeError((temp / "core.log").read_text(errors="replace"))
                try:
                    if request(API + "/files")[0] == 200:
                        break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError((temp / "core.log").read_text(errors="replace"))

            assert request(API + "/files", authenticated=False)[0] == 401
            assert request(API + "/file", "PUT", {"id": "claude", "version": "missing", "content": "bad"}, False)[0] == 401
            code, page = request("/v0/resource/plugins/agent-instructions/editor", authenticated=False)
            assert code == 200 and b"<!doctype html>" in page
            assert b"Explain changes clearly" not in page
            listing = api("/files")["files"]
            for id, relative in [("kimi", "kimi-code/AGENTS.md"), ("grok", ".grok/AGENTS.md"), ("zcode", ".zcode/AGENTS.md"), ("antigravity", ".gemini/GEMINI.md"), ("antigravity-agents", ".gemini/AGENTS.md")]:
                file = next(f for f in listing if f["id"] == id)
                assert Path(file["path"]) == temp / relative, (id, file["path"])
                created = api("/file", "PUT", {"id": id, "version": "missing", "content": "# Original " + id})
                changed_new = api("/file", "PUT", {"id": id, "version": created["version"], "content": "Updated"})
                api("/file", "PUT", {"id": id, "version": created["version"], "content": "Stale"}, 409)
                backup = api("/backups?id=" + id)["backups"][0]["name"]
                restored_new = api("/restore", "POST", {"id": id, "version": changed_new["version"], "backup": backup})
                assert restored_new["content"] == "# Original " + id
                assert (temp / relative).read_text() == restored_new["content"]
            first = next(f for f in listing if f["id"] == "claude")
            assert "<example> & code" in first["content"], "Core must not HTML-escape file content"
            changed = api("/file", "PUT", {"id": "claude", "version": first["version"], "content": "# Updated\n<literal> & café\n"})
            assert changed["content"] == "# Updated\r\n<literal> & café\r\n"
            api("/file", "PUT", {"id": "claude", "version": first["version"], "content": "stale"}, 409)
            backups = api("/backups?id=claude")["backups"]
            assert len(backups) == 1
            restored = api("/restore", "POST", {"id": "claude", "version": changed["version"], "backup": backups[0]["name"]})
            assert restored["content"] == first["content"]
            api("/file", "PUT", {"id": "../config.yaml", "version": "missing", "content": "bad"}, 400)
            api("/restore", "POST", {"id": "claude", "version": restored["version"], "backup": "../../config.yaml"}, 400)
            override = api("/file", "PUT", {"id": "codex-override", "version": "missing", "content": "Temporary rules"})
            assert override["overrideActive"]
            cleared = api("/file", "PUT", {"id": "codex-override", "version": override["version"], "content": ""})
            assert not cleared["overrideActive"]
            # External writes must not be lost to an already-open editor.
            (claude / "CLAUDE.md").write_text("External edit", encoding="utf-8")
            api("/file", "PUT", {"id": "claude", "version": restored["version"], "content": "stale"}, 409)
            assert (claude / "CLAUDE.md").read_text() == "External edit"
            (claude / "CLAUDE.md").write_bytes(first["content"].encode())
            print("PASS: real-core loading, authentication, exact Markdown round trip, save, conflict, backup, restore, allowlist, override", flush=True)
            if args.serve:
                print(f"PREVIEW_URL={base}/v0/resource/plugins/agent-instructions/editor", flush=True)
                print(f"FIXTURE_HOME={temp}", flush=True)
                print(f"TEST_KEY={KEY}", flush=True)
                process.wait()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
