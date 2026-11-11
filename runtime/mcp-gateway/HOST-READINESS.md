# Central Windows host readiness

Prepared for the intended Windows 11 central host. No model
inference runs here. The final Windows/Tailscale identity is still pending. The
JetKVM address is not a gateway destination. Nothing in this bundle deploys there.

## Install only the roles you need

| Program | Role | Required now? | Version evidence |
|---|---|---|---|
| Tailscale for Windows | Private reachability and device access controls | Yes for shared access | Verify current approved Windows release and unattended mode on target |
| Native CLIProxyAPI core | Supported model/provider API routing | Yes for provider routing | Existing development installation has 8.0.63; target release must be checked separately |
| ECPA desktop + Connections Manager | Management UI | Yes for ECPA management | Connections Manager 0.8.0; install from its dedicated release repository |
| 64-bit Python | SDK gateway worker | Yes | Tested Python 3.13.6; package supports >=3.12. Use an approved patched 3.13 release and rerun checks |
| Bitwarden Secrets Manager CLI (`bws`) | Resolve individual secret UUIDs | Yes for Bitwarden profiles | Tested 2.1.0, EU and US region selection |
| `ecpa-connect.exe` | Shared Portainer and verified SSH operations | For Portainer/SSH | Build matching Connections Manager 0.8.0; ship binary, no Rust compiler needed on host |
| T3 | Existing agent/workspace orchestration | If this host runs that role | Pin the chosen tested release at deployment; Windows unattended startup remains a separate validation |
| Node.js/npm | Node MCP packages / Wrangler / T3 if its installation requires Node | Only for those roles | Pin a supported LTS version compatible with each package; not needed by the Python gateway |
| Wrangler | Explicit Cloudflare CLI jobs | Optional | Inspected installed 4.109.0; no live deploy test performed |
| PowerShell 7 | Administration | Recommended | Scripts use Windows PowerShell-compatible task APIs; record installed version |
| Git | Fetch/update sources, workspace jobs | Optional | Runtime package does not require Git |
| Codex, Claude, other agent CLIs | Execute jobs on this machine | Optional | Install only for assigned runner roles; client laptops can access gateway without central agent CLIs |

No Docker, WSL, inference stack, compiler or shared database is required for this
gateway. Build binaries/wheels on a development worker. Keep heavy builds and
model inference on other workers/providers. Allow at least 2 GiB free for gateway
dependencies/logs plus space for ECPA/T3/workspaces; Modest host RAM calls for conservative
connector concurrency. Current worker caps tool execution at eight simultaneous
operations; fresh connector processes consume memory according to their package.

Windows 11 is the accepted deployment target. Hardware replacement is planned;
preparation does not depend on it. Keep installation/data paths, task name and
logical host ID explicit. On the replacement Windows machine, import non-secret
definitions, install the pinned runtime, and re-bootstrap credentials under the
new task identity. DPAPI files and user-bound vault entries are not portable backups.

## Identity and initial bootstrap

1. Choose a dedicated standard Windows account with a password and outbound
   HTTPS access. Decide its runtime directory, e.g. `C:\ECPA\gateway-0.2.0`.
   Sign into that account for initialization. ECPA's management bridge currently
   needs the same identity/vault and `gateway-runtime.json` in its Connections
   Manager data directory. A separate ECPA identity requires an explicit future
   authenticated management integration; do not copy another user's vault.
2. Install the trusted Python and BWS binaries. Copy the reviewed runtime bundle
   and matching helper. Run `windows/Install-Runtime.ps1` with absolute `-Python`,
   `-Destination`, `-Helper`, `-Bws`, and a stable `-HostId`. Installation does not
   create a startup task, firewall rule or network exposure. It refuses an existing
   destination and restricts the directory to this account, SYSTEM and admins.
3. In Bitwarden Secrets Manager create a machine account with only the projects/
   secrets this host needs. Use EU for the existing pilot. Securely set its machine
   token as `BWS_ACCESS_TOKEN` in the bootstrap account's environment, without
   putting the value in scripts, shell history, chat or source. Run:

   ```powershell
   & $RuntimePython -m ecpa_gateway.cli --config $Config bootstrap-bws
   & $RuntimePython -m ecpa_gateway.cli --config $Config doctor --network
   ```

   `bootstrap-bws` stores it in that account's Windows Credential Manager; remove
   the temporary environment variable afterward. It is given only to BWS. Each
   service receives its own resolved value. No credentials have been transferred
   from this development PC to the pending central host.
4. Run `serve` in a test terminal. Save/test a reference-only sample profile, then
   a Portainer profile, using the ECPA wizard or `admin --request-file`. First test
   initializes/lists tools; publication requires an exact reviewed allowlist.
   Read an environment/container for Portainer; never deploy or generate paid
   Runway media for a health test.
5. Run `doctor --protocol` as the intended task account. It reports versions,
   free disk, identity, local port, vault access and authenticated MCP handshake.
   `--network` checks public Bitwarden HTTPS reachability without sending secrets.
   It never dumps environment variables or credential values. A passing doctor
   is not proof of upstream grants or reboot persistence.

## Unattended operation and acceptance

The gateway is a Python background process, separate from ECPA's desktop UI and
CLIProxyAPI's model-routing core. Use `Register-GatewayTask.ps1` from an elevated
administration session with `-Credential (Get-Credential)` for the exact account
used above. `-WhatIf` previews registration. It uses password logon at startup,
limited privileges, restart on failure and no execution timeout. It rejects a
different credential SID and existing task; no S4U fallback is used because its
credential/network behavior differs. Check local policy permits batch logon.

This task installer has static validation here; target registration, sign-out and
reboot remain **pending**, not proven. Verify in this order on the final host:

1. Start only the new task. Check Task Scheduler state/last result, then run
   `doctor --protocol` under its identity and call sample status from a client.
2. Close ECPA's desktop window. Verify the gateway again and separately make a
   harmless authenticated request to CLIProxyAPI. Core survival must be tested;
   do not assume the desktop-owned core survives because the gateway does.
3. Sign out the runtime account. Verify gateway and required core/T3 endpoints
   from another authorized Tailscale machine. A task using interactive logon
   only fails this requirement.
4. Reboot. Before desktop login, repeat remote MCP initialize/list and sample
   status, core/provider routing and T3 health checks. Record results/versions.
5. Test restart-on-failure using only the dedicated gateway task/process. Never
   stop production T3/ECPA services while developing this bundle.

T3 documentation currently describes `t3 service install` for macOS/Linux only.
Do not present it as Windows support. Validate the actual installed T3 foreground
server command and its credential/profile identity before defining a separate
Windows startup task. No T3 command or task is installed by this bundle. Likewise
configure a separate supported CLIProxyAPI core startup mode once verified for
the selected version; avoid competing desktop-managed and scheduled core copies.

## Private network boundary and client setup

Keep the worker on `127.0.0.1:8769`; parameterize the port. Use the final Tailscale
identity with an authenticated HTTPS reverse proxy restricted to `/mcp`. Keep
`/admin` and `/provider` inaccessible remotely, disable public Funnel, limit Tailscale ACLs to the
intended devices/users and verify the proxy's Host header against `allowed_hosts`.
Select/configure the proxy when the host identity is known; this bundle does not
guess the hostname, open firewall ports or claim TLS is configured. Test an
unauthenticated request returns 401 and a remote `/admin` request is unavailable.
Set `public_url` in the runtime config to that exact HTTPS `/mcp` endpoint and
restart the worker; keep `url` as its local loopback management address. The
default host/origin policy accepts only those two configured endpoints. An
explicit `allowed_hosts` override must retain the loopback host and port so the
local management bridge continues to work.

Each client generates its own bearer key locally:

```powershell
& $ClientPython -m ecpa_gateway.cli --config $ClientConfig client-init --url https://FINAL-TAILSCALE-NAME/mcp --identity laptop-codex
```

Only a SHA-256 fingerprint is printed. On the central host, register that public
fingerprint with explicit `grant-client --identity laptop-codex --sha256 HASH
--service cloudflare-work-read --group work --project my-project`. Register one
SDK bridge in Codex/Claude using `-m ecpa_gateway.cli --config CLIENT_CONFIG bridge
--identity laptop-codex`. The client needs Python/the gateway package; it needs no
BWS machine token or service key. Direct HTTP clients may use their own secure
bearer storage; avoid plaintext shared config. `revoke-client --identity ID`
denies new requests immediately; already-running calls may finish.

The local ECPA client-setup UI previews narrow edits and creates backups. Preserve
existing direct Portainer until its gateway replacement is verified. Config
updates require agents to reconnect/reload tools; this does not change a running
conversation's tool list automatically.

## Routine operation

Rotate service secrets in Bitwarden: they resolve on each connection, with no
catalogue key copy. Rotate the BWS machine token under the runtime identity and
repeat bootstrap. OAuth requires an explicit interactive sign-in on that runtime
host (`oauth-login --profile ID`); do not assume a remote browser callback works.
OAuth files use that Windows account's DPAPI. A new host/identity needs bootstrap
and authorization again, even if reference-only manifests are copied.

Manage service/account/tool policy in Connections Manager, durable secrets in
Bitwarden, installed packages/startup on the host, model routing in CLIProxyAPI,
and execution/workspace assignment in the existing T3 runner. A gateway does not
move workspaces, synchronize skills or create a multi-machine scheduler.

Keep versioned runtime installations. Back up protected config/catalogue files;
reference-only export does not export credentials. Restore catalogue backups with
version checks, or client config transactions only when files have not changed
since apply. For upgrades stop only the gateway task, install a tested version,
update its action explicitly, and run protocol/pilot tests before migration.
Retain the old installation/action for rollback. Do not downgrade schemas blindly.

Next useful increments: machine capability inventory using existing runners,
redacted activity/health and credential-expiry alerts, provider-supported quotas,
versioned skill bundles with explicit client sync, and staged updates. These are
priorities, not claims that a new orchestrator or billing collector is implemented.

## Upgrade from 0.1 to 0.2

Upgrade the DLL to Connections Manager 0.8.0 and, for machine management, SSH &
Machines 0.2.0. The separate gateway bundle is 0.2.0. Updating a DLL does not update
an already installed worker. The normal installer refuses existing configuration;
this deliberate protection must not be bypassed by deleting runtime data.

For an existing worker, use a side-by-side installation under the **same runtime
Windows identity**. Before making changes, privately back up `gateway-runtime.json`,
`mcp-services.json`, requests and catalogue/client backups; record the existing task
action and package versions. Restrict these backups to that account/admins. Do not
export vault values or commit this directory. Keep the old runtime installation.

1. Extract the verified 0.2.0 bundle into a new protected directory. Create a new
   venv there with your approved Python version. Install its locked dependencies
   and package, without running `init` or the fresh-install script:

   ```powershell
   & $Python -m venv "$NewRuntime\venv"
   $NewPython = "$NewRuntime\venv\Scripts\python.exe"
   & $NewPython -m pip install --only-binary=:all: -r "$Bundle\requirements-windows.lock"
   & $NewPython -m pip install --no-deps --no-build-isolation $Bundle
   Copy-Item -LiteralPath "$Bundle\ecpa-connect.exe" -Destination "$NewRuntime\ecpa-connect.exe"
   ```

   `$Bundle`, `$NewRuntime`, `$Python` and `$Config` are your reviewed absolute paths.
   Use a new destination; restrict its ACL to the runtime account, SYSTEM and admins
   using the same policy as `Install-Runtime.ps1`. Stop if any install command fails.
2. Stop **only the dedicated gateway task/process**. Do not stop T3 or unrelated
   ECPA services. Test the new worker in the foreground using the existing config:
   `& $NewPython -m ecpa_gateway.cli --config $Config serve`. It uses the existing
   identity/vault and catalogue; no credential re-bootstrap is needed on the same
   machine/account. In Runtime & recovery select the new shared helper and, when
   used, the actual SSH catalogue directory. Test sample/Portainer reads and doctor.
3. Stop that foreground worker. Update only the gateway task's executable/action
   to `$NewPython -m ecpa_gateway.cli --config "$Config" serve`, preserving its
   reviewed principal, password-logon mode, trigger and restart settings. Start
   it and repeat protocol checks. Registration scripts intentionally refuse to
   overwrite existing tasks; review the action in Task Scheduler or use an explicit
   `Set-ScheduledTask -Action` update. Sign-out/reboot tests still belong on the
   actual central host. Reload core/plugin model registration for new model aliases.
4. Existing local agent bridges still reference their earlier Python installation.
   Keep it until **Connect agents** has previewed/applied the new bridge path and
   each client reconnects successfully. Remote clients can keep a compatible bridge;
   no service secrets are copied to them.
5. To roll back, stop only this gateway, restore the pre-upgrade catalogue/config
   and previous task action, and restart. New profile kinds are not understood by
   0.1.0; do not point old code at an edited 0.2 catalogue. Roll back client entries
   only through unchanged-file transaction checks. Preserve private request history
   and inspect any `running`/uncertain operation before another attempt.

An upgrade on this development PC has not been applied automatically. New-host
installation, private TLS exposure, actual service identity and reboot persistence
remain pending final host setup. No real Cloudflare deployment, paid Runway job,
provider inference or remote SSH restart is part of release verification.
