# SSH & Machines

Windows x64 native ECPA plugin, version 0.1.0. Manage named machine profiles and
verify their SSH identity from the ECPA host. It does not create a new job scheduler.

## Set up a machine

1. Install **Windows OpenSSH Client** on the ECPA host. On the target, enable and
   configure an SSH server separately; this plugin never installs one remotely.
2. Open **Plugins → SSH & Machines**, unlock with the ECPA management key, and
   choose **Add machine**. Supply its hostname/Tailscale name, SSH port, username,
   remote OS and optional labels.
3. Select an existing private-key file or the SSH agent. All paths refer to the
   **ECPA host**, not the computer displaying its web page. Agent mode requires
   the matching `.pub` file to select one identity. The ECPA process/task must run
   as the Windows account with access to that key or agent. Automated key-file
   checks cannot prompt for a passphrase; use agent mode for protected keys.
4. Scan advertised host keys or paste the public host key. A scan is unauthenticated:
   independently compare its SHA256 fingerprint using the target console or a
   trusted administrator/channel. Enter the verified fingerprint and save.
5. **Test connection** verifies the pinned host key and selected public-key identity,
   then runs fixed OS/username diagnostics (`uname -s; id -un` or Windows `ver` and
   `whoami`). It does not install software, deploy, restart, delete, or modify files.

No real machine is added or contacted automatically. Choose the operating system
explicitly; diagnostics do not guess a different account or OS on failure.

## Keys, terminals and permissions

Private key bytes/passwords/API tokens are not accepted by the plugin API, UI or
catalogue. OpenSSH reads the chosen file/agent. Identity selection is explicit;
password fallback, agent forwarding, inherited SSH config, proxy commands,
forwardings and shared control connections are disabled. Host keys must match the
saved pin; a changed key needs deliberate independent verification and profile edit.

**Get terminal command** generates a quoted PowerShell command for an interactive
terminal on the ECPA host. It never launches a window automatically. An interactive
SSH terminal has whatever privileges the remote account grants and is **not read-only**.
Prefer restricted target accounts and keys; the plugin does not create an OS sandbox.

This first release is an administrator management surface. It exposes no arbitrary
remote-command endpoint, agent SSH MCP, maintenance-command editor, secret resolver,
file transfer, SSH tunnel or T3 runner registration. Labels are inventory metadata,
not execution permissions. Use existing T3/environment registration for authorised
jobs. Shared agent access requires a separate explicit policy/runner integration.
The existing Connections Manager/Bitwarden workflow remains the service-secret
home; SSH uses existing keys/agent instead of introducing another credential vault.

## Storage, migration and recovery

Defaults to `%LOCALAPPDATA%\ECPA\ssh-machines`; `data_dir` can select an absolute
alternative. `machines.json` stores machine names, hosts/users, public host keys,
key paths and labels. Writes use locking, expected-version checks and atomic replace.
The previous catalogue is retained as `machines.before.json`. Restore it only while
the plugin is idle and after preserving current changes; private keys are untouched.

Profile exports include private **inventory metadata** and local key paths, but no
private key bytes or passwords. Keep exports/backups outside public repositories.
Import one machine object through the review wizard; no immediate connection occurs.
On a replacement host, re-provision keys/agent under its runtime identity, update
paths, and verify fingerprints again. A user-bound agent/vault does not migrate by
copying these JSON files. Existing live SSH sessions may finish after profile edits.

ECPA authenticates `/v0/management/ssh-machines/state` and `/action`. The unauthenticated
editor resource contains only static UI. Child stderr is suppressed, connection
checks time out after 15 seconds, output is bounded, and remote text is rendered
as text. Results are untrusted remote data, never instructions.

## Build and verification

From the source workspace:

```powershell
cargo test -p ssh-machines
python scripts/package.py --plugin ssh-machines
python -m pip install -r plugins/ssh-machines/tests/requirements.txt
python plugins/ssh-machines/tests/integration.py --core PATH_TO_TEST_CORE
```

The integration uses an isolated core, temporary keys and a synthetic loopback SSH
server. It checks authentication, key scanning/pinning, real SSH command execution,
wrong-key rejection, stale-edit protection, export privacy and API boundaries.
No production SSH server, Windows account login, central host or T3 userdata is used.
