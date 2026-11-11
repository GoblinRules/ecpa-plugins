# SSH and Machines

Windows x64 native ECPA plugin, version 0.2.1. Manage named machine profiles and
verify their SSH identity from the ECPA host. It does not create a new job scheduler.

## Set up a machine

1. Install **Windows OpenSSH Client** on the ECPA host. On the target, enable and
   configure an SSH server separately; this plugin never installs one remotely.
2. Open **Plugins → SSH and Machines**, unlock with the ECPA management key, and
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

## Management login

**Remember key on this device** is optional. It shares the browser's saved management
key with Connections Manager and other ECPA suite plugins on the same origin. Without
it, the key lasts only for the current tab session. **Lock & forget** removes this
plugin's tab key and the shared saved key; other already-open plugins may still hold
their own session keys. Rejected credentials are cleared; temporary network failures
retain them. Automatic unlock only reads the catalogue, never starts an SSH connection.

This is browser storage, not native ECPA single sign-on or encrypted credential storage.
Other pages on this origin can read the saved key. Avoid remembering it on shared devices.
If browser storage is blocked, manual unlock still works. OpenSSH private keys are never
copied into browser storage. The display name uses ?and? because some ECPA versions
HTML-escape ampersands in metadata displayed by their sidebar.

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

For agent access, open Connections Manager 0.8.0 with gateway 0.2.0, add **Saved
SSH machine**, and select the machine ID. Test/publish fixed diagnostics and, if
needed, predefined service restarts. Assign explicit client/group/project grants.
Each restart requires a separate human approval in Connections Manager. Requests
bind the saved machine, selected identity file and host-key pin; changes require
retesting. No arbitrary remote shell tool, file transfer, tunnel, software install
or T3 runner registration is exposed. Use existing T3 runners for broader jobs.
The shared Connections Manager helper executes these fixed operations; no extra
per-machine executable is required. The runtime must run under the identity with
access to the saved keys/agent and SSH catalogue.

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
wrong-key rejection, stale-edit protection, export privacy, gateway machine bindings,
approval-required restarts, replay rejection and API boundaries.
No production SSH server, Windows account login, central host or T3 userdata is used.
