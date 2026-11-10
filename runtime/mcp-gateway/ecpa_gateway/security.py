"""Credential references and process isolation. Never return secrets from management APIs."""
import asyncio
import hashlib
import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


class SafeError(Exception):
    """Only static, credential-free messages may be supplied."""


REGIONS = {"eu": "https://vault.bitwarden.eu", "us": "https://vault.bitwarden.com"}
RUNTIME_ENV = {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "PATH", "PATHEXT", "TEMP", "TMP",
               "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
               "HOME", "LANG", "LC_ALL", "TMPDIR"}
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SENSITIVE = re.compile(r"(?i)(token|secret|password|authorization|api.?key|credential)")
TOKEN_LITERAL = re.compile(r"(?i)(Bearer\s+\S+|gh[pousr]_[a-z0-9]+|github_pat_[a-z0-9_]+|sk-[a-z0-9_-]{12,}|ptr_[a-z0-9_]+)")


def clean_env():
    return {k: v for k, v in os.environ.items() if k.upper() in RUNTIME_ENV}


def user_env(name):
    value = os.environ.get(name)
    if not value and os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value = winreg.QueryValueEx(key, name)[0]
        except OSError:
            pass
    if not isinstance(value, str) or not value.strip():
        raise SafeError("Required runtime credential environment variable is missing.")
    return value


def vault_get(target):
    if os.name != "nt":
        raise SafeError("Windows credential references require a Windows runtime.")
    from .winvault import get
    return get(target)


def vault_put(target, value):
    if os.name != "nt":
        raise SafeError("Use mounted secret files to bootstrap a Linux runtime.")
    from .winvault import put
    put(target,value)


def auth_target(directory, identity):
    digest = hashlib.sha256(str(Path(directory).resolve()).encode()).hexdigest()[:24]
    return f"ECPA/MCP/{digest}/{identity}"


def auth_secret(config, identity):
    entry = config["identities"][identity]
    if entry.get("vault_target"):
        return vault_get(entry["vault_target"])
    path = Path(entry["secret_file"])
    if not path.is_absolute():
        raise SafeError("Client secret file must be an absolute path.")
    return path.read_text().strip()


def token_digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def authenticate(config, bearer):
    if not bearer.startswith("Bearer ") or len(bearer) > 1024:
        return None
    digest = token_digest(bearer[7:])
    for identity, entry in config["identities"].items():
        if secrets.compare_digest(digest, entry["sha256"]):
            return identity
    return None


def validate_url(value, *, origin_only=False, private_http=False):
    try:
        u = urlsplit(value)
        port = u.port
    except ValueError:
        raise SafeError("Invalid service URL.") from None
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.fragment or u.query:
        raise SafeError("Use an HTTP(S) URL without credentials, query or fragment.")
    if origin_only and u.path not in ("", "/"):
        raise SafeError("Use a service origin without a path.")
    if u.scheme == "http" and not private_http and u.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise SafeError("HTTP requires explicit acknowledgement of a trusted private network.")
    return value


def validate_reference(ref):
    if not isinstance(ref, dict):
        raise SafeError("A credential reference is required; literal credentials are not accepted.")
    provider = ref.get("provider")
    if provider == "bitwarden":
        if ref.get("region") not in REGIONS or not UUID.fullmatch(ref.get("secret_id", "")):
            raise SafeError("Select a Bitwarden region and valid secret UUID.")
        allowed = {"provider", "region", "secret_id"}
    elif provider == "windows-vault":
        if not isinstance(ref.get("target"), str) or not ref["target"].startswith("ECPA/"):
            raise SafeError("Choose an ECPA Windows credential target.")
        allowed = {"provider", "target"}
    else:
        raise SafeError("Supported credential sources are Bitwarden Secrets Manager and Windows Credential Manager.")
    if set(ref) - allowed:
        raise SafeError("Credential references must contain only provider/region/UUID or vault target.")


async def bounded_process(command, env, timeout=30):
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        child = await asyncio.create_subprocess_exec(*command, env=env, stdin=subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE, stderr=subprocess.DEVNULL, **flags)
        async with asyncio.timeout(timeout):
            output = b''
            while True:
                chunk=await child.stdout.read(4096)
                if not chunk:break
                output+=chunk
                if len(output) > 65536:
                    raise SafeError("Credential helper response exceeded its limit.")
            await child.wait()
        if child.returncode:
            raise SafeError("Bitwarden denied access or its machine token expired; check the secret grant and region.")
        return output
    except (TimeoutError, OSError):
        raise SafeError("Credential helper unavailable or timed out. Verify bws installation and connectivity.") from None
    finally:
        if "child" in locals() and child.returncode is None:
            child.kill()
            await child.wait()


async def resolve(ref, config):
    validate_reference(ref)
    if ref["provider"] == "windows-vault":
        value = vault_get(ref["target"])
    else:
        cli = Path(config["bws_executable"])
        if not cli.is_absolute() or not cli.is_file():
            raise SafeError("Bitwarden CLI is missing; set its absolute path in runtime settings.")
        # The machine token is delivered ONLY to bws, never to MCP children.
        if config.get("bws_token_file"):
            token = Path(config["bws_token_file"]).read_text().strip()
        elif config.get("bws_vault_target"):
            token = vault_get(config['bws_vault_target'])
        else:
            token = user_env("BWS_ACCESS_TOKEN")
        raw = await bounded_process([str(cli), "secret", "get", ref["secret_id"], "--server-url",
                     REGIONS[ref["region"]], "--output", "json", "--color", "no"],
                     {**clean_env(), "BWS_ACCESS_TOKEN": token})
        del token
        try:
            record = json.loads(raw)
            if record["id"].lower() != ref["secret_id"]:
                raise ValueError()
            value = record["value"]
        except (ValueError, KeyError, TypeError, AttributeError):
            raise SafeError("Bitwarden returned an invalid secret response.") from None
    if not isinstance(value, str) or not 1 <= len(value) <= 8192 or any(ord(c) < 32 for c in value):
        raise SafeError("Credential is empty, oversized or contains control characters.")
    return value


def redact(value):
    """Best-effort display redaction. Exported managed definitions forbid literal bindings."""
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if SENSITIVE.search(k) and k not in ("secret_id", "credential_refs") else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return TOKEN_LITERAL.sub("[REDACTED]", value)
    return value
