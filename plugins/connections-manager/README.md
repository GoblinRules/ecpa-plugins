# Connections Manager

Named Cloudflare, GitHub and Portainer connections for agents and tools, with a bundled helper and Windows Credential Manager storage. Windows x64, version 0.8.1.

## Install

Add the [ECPA Plugins registry](https://raw.githubusercontent.com/GoblinRules/ecpa-plugins/master/registry.json), install **Connections Manager**, and open its page. Unlock with the proxy management key. The management key can be remembered on this device; account tokens are stored in **Windows Credential Manager**, never in the catalogue or agent instructions.

The release DLL includes its matching `ecpa-connect.exe`. When the plugin loads, it installs or updates one shared copy at:

```text
%LOCALAPPDATA%\ECPA\helpers\connections-manager\ecpa-connect.exe
```

Open **Settings → Shared helper** to see its version, location and readiness. **Verify helper** runs a noninteractive executable/version check. No separate installer or download is needed. Installation uses a temporary file, SHA-256 comparison and atomic replacement; if an agent is using the old executable, it is preserved. Stop the affected agent/MCP process, then click **Install / repair**. The account catalogue and vault are not changed by helper installation.

**Upgrading from 0.5.x:** existing agent configurations continue using their old helper path. Regenerate and merge each MCP entry once to adopt the managed location, then restart that MCP server. New entries use distinct names such as `ecpa-portainer-demo`; remove the superseded `named-connection` entry yourself to avoid running both. Future plugin updates use the same managed path. Existing running processes must restart to use a new helper version.

Advanced users can opt into a custom executable under **Settings → Advanced**. Its location is browser-local, must be verified before generation, and must be updated manually. The standalone helper and `checksums.txt` remain available in the [release repository](https://github.com/GoblinRules/ecpa-connections-manager/releases/latest). Older saved custom locations are retained, but managed mode is the new default.

The core, helper and agents must run as the **same Windows user**. A core running as a Windows service account has a different credential vault. This release manages local connections; it does not synchronize credentials to other computers.

## Add accounts

The setup wizard walks through service, authentication method, details and review. After saving, use **Verify account** to check service access, then **Connect a tool or agent**. The status distinguishes a saved credential from a successful account check; results are session-only and clear when you refresh or edit the account. A passed account check does not mean an agent is configured.

Create one connection per account: e.g. `cf-personal`, `cf-work`, `cf-client-a`, `gh-personal`, `gh-work`. IDs are stable lowercase letters, digits and hyphens. Display names can be edited freely. A connection's service cannot be changed. A blank token when editing keeps the saved token; entering a token replaces it.

- **Cloudflare:** supply the 32-character account ID and a scoped API token. Choose permissions needed by your work. **Verify account** calls the account-details endpoint and requires Account Settings: Read. A token can work for deployment but fail this identity check if it lacks that read permission. Account-scoped tokens and user API tokens are supported when they can access that account endpoint.
- **GitHub:** supply a GitHub.com personal access token with access to the repositories you need. Verification identifies the authenticated user; it does not prove access to every repository.

Verification connects only to `api.cloudflare.com` or `api.github.com`, with TLS and redirects disabled. It returns account identity, not the token. Corporate proxy support is limited to the HTTP client's supported environment configuration; it does not inherit the core's custom transport settings.

## Project assignments

Assign a Cloudflare and/or GitHub connection to an existing absolute project directory. The helper resolves the nearest assigned ancestor, so a nested project can override its parent. Running with `--project` also sets the child process's working directory to that directory. Choose None for both services to remove an assignment. Assigned connections cannot be deleted until those references are removed.

Assignments are local metadata, not automatic modifications to agent configs. A normal `wrangler` or `gh` invocation still uses that tool's normal credentials. Use the helper to select managed connections.

## CLI usage

```powershell
& "$env:LOCALAPPDATA\ECPA\helpers\connections-manager\ecpa-connect.exe" list
& "$env:LOCALAPPDATA\ECPA\helpers\connections-manager\ecpa-connect.exe" check cf-work
& "$env:LOCALAPPDATA\ECPA\helpers\connections-manager\ecpa-connect.exe" run --connection gh-work -- gh.exe repo list
& "$env:LOCALAPPDATA\ECPA\helpers\connections-manager\ecpa-connect.exe" run --project 'C:\Projects\client-site' -- gh.exe auth status
& "$env:LOCALAPPDATA\ECPA\helpers\connections-manager\ecpa-connect.exe" run --connection cf-work -- node.exe 'C:\Projects\client-site\node_modules\wrangler\bin\wrangler.js' whoami
```

On Windows, use `node.exe` plus Wrangler's JavaScript entry point instead of the `wrangler.cmd` shim. The helper rejects `.cmd`, `.bat` and `.ps1` entry points. It passes arguments directly to the selected executable, with no constructed shell command. For agents distributed as npm shims, use the corresponding Node entry point too.

Cloudflare supplies `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`. GitHub supplies `GH_TOKEN`, `GITHUB_TOKEN`, `GITHUB_PERSONAL_ACCESS_TOKEN` and `GH_HOST=github.com`. Competing inherited variables for these services are removed from the child environment. The parent shell and global login files are unchanged. Multiple processes can therefore use different accounts concurrently. Other tool config files and command flags still apply: check Wrangler's account configuration for conflicts with the selected account.

The launched process and its children can read the selected tokens. Use trusted executables and MCP servers. Tokens never appear in helper arguments or helper logs, but a child process could print its own environment. This is account selection, not an OS sandbox.

GitHub CLI authentication is not a Git SSH identity manager. Git's SSH keys/HTTPS credential helpers and browser logins are separate. GitHub Enterprise and remote OAuth MCP session brokering are not implemented.

## Claude / Codex / MCP Manager

The **Use with agents & tools** page generates PowerShell commands and Claude JSON or Codex TOML snippets. Select the separately installed MCP server executable and its arguments, then merge the generated server entry into the agent config. You can also paste the individual Claude server definition into MCP Manager's advanced editor and use its preview/apply flow. Tokens stay out of those files.

The generator displays the selected account names/IDs and uses a distinct MCP entry name per account or project. It rejects missing credentials, helper self-launches and shell shims. In this local-helper generator, only Portainer has a built-in MCP server. The separate shared gateway below also provides Cloudflare, Runway and SSH adapters. Cloudflare and GitHub require a compatible external stdio MCP server for this workflow; the helper itself, GitHub CLI and Wrangler are not those servers. Remote OAuth MCP endpoints belong in the agent’s own MCP setup.

The helper passes through stdin/stdout and the child exit code; its account selection message goes to stderr, preserving stdio MCP framing. Only token-based servers accepting the listed environment variables are supported. Remote OAuth-only servers need their own login flow.

To use a whole agent session with a project's connections, launch the agent executable through `run --project ...`; its child CLI processes inherit the environment. This does not install a Codex plugin, Claude extension or change instructions automatically.

## Storage and recovery

Default catalogue: `%LOCALAPPDATA%\ECPA\connections-manager\connections.json`. Only connection names, IDs, account IDs and project assignments are stored there. `data_dir` in the plugin's settings accepts an absolute directory; pass the same directory to the helper with `--data-dir PATH` **before** its command. The UI includes it in generated commands.

Credential targets are namespaced by the catalogue directory. Moving the catalogue or changing `data_dir` requires re-entering tokens; copying the JSON alone does not transfer credentials. Catalogue writes are locked and atomic, and stale browser saves are rejected. Do not manually edit the catalogue while tools are using it. Deleting a connection removes its vault token; uninstalling the DLL intentionally preserves both metadata and credentials. Delete connections first if you want them removed.

## Development and verification

```powershell
cargo test -p connections-manager --locked
cargo clippy -p connections-manager --all-targets --locked -- -D warnings
python scripts/package.py --plugin connections-manager
python plugins/connections-manager/tests/integration.py --core C:/path/to/cli-proxy-api.exe
```

The real-core test creates uniquely scoped synthetic credentials, verifies process isolation and removes those credentials in cleanup. `--serve` leaves the synthetic fixture available for the documented browser test until stopped. No personal credentials are used.

References: [Wrangler environment variables](https://developers.cloudflare.com/workers/wrangler/system-environment-variables/), [GitHub CLI environment](https://cli.github.com/manual/gh_help_environment).

## GitHub browser sign-in (introduced in 0.2.0)

Use **Add an account → Sign in with GitHub CLI** to generate a PowerShell command, or run:

```powershell
& "$env:LOCALAPPDATA\ECPA\helpers\connections-manager\ecpa-connect.exe" login-github gh-work 'GitHub Work'
```

Install GitHub CLI first; packaged plugins manage the helper version automatically. Finish the browser/device-code flow, then type the verified username in the terminal. Click Refresh in the plugin. Each new ID is independent; existing IDs cannot be overwritten by this command. The resulting OAuth token uses the same Windows vault and per-process selection as API tokens. Reauthenticate with a new connection if GitHub revokes the token; this is not a generic OAuth refresh broker.

The helper uses an ephemeral `GH_CONFIG_DIR` and `--insecure-storage` because gh's system credential entries are not isolated by its config directory. It imports the token into Windows Credential Manager and deletes the temporary profile on normal success, error or cancellation. Forced process termination or machine failure can leave an `ecpa-github-login-*` folder in the current user's temporary directory containing the token; remove that leftover folder. No global gh login is changed. No sign-in is performed from the web server process.

**Agent setup:** choose a saved account and a local stdio MCP server under **Connect a tool or agent**, generate Claude or Codex configuration, merge it into that agent's MCP configuration, then restart the server. GitHub CLI and Wrangler themselves are not MCP servers. Alternatively launch a new agent executable through the helper so its child tools inherit the account. Existing agent sessions are unaffected.

Wrangler OAuth profiles and remote MCP OAuth remain unsupported by this helper. Use a Cloudflare API token for Wrangler, and the agent's own OAuth flow for a remote MCP server. A Wrangler OAuth session is not interchangeable with an MCP OAuth session.

Validation: Rust tests, native-core integration and responsive Edge tests pass. `tests/login.py` tests the browser-login orchestration with a native fake gh, synthetic credentials and the real Windows vault, including cancellation and cleanup. Real GitHub authorization requires the user's interactive browser consent and was not performed by automated tests.

## Use an existing local GitHub login (0.3.0)

In **Add an account → Use an existing GitHub login or sign in**, keep **Use an existing local GitHub login** selected. Set a new connection ID and display name using the shared helper, then generate and run the command in PowerShell:

```powershell
& "$env:LOCALAPPDATA\ECPA\helpers\connections-manager\ecpa-connect.exe" import-github gh-work 'GitHub Work'
```

The terminal lists saved github.com accounts from GitHub CLI. Choose a number, then confirm the verified username. Refresh the plugin afterwards. No browser sign-in is needed. Requires a recent GitHub CLI with `auth status --json` and `auth token --user` support. Discovery respects your shell's `GH_CONFIG_DIR` and Windows user; inherited token environment variables are ignored so they cannot override the chosen saved account. The import never runs `gh auth switch` or modifies the source profile.

The saved credential is a **copy**, not a live link: revoking the original invalidates it, and later replacing a gh login does not automatically update this connection. Existing connection IDs are protected against overwrite. Identity verification requires network access and rejects an account mismatch. Tokens are never included in generated commands or printed by the helper.

This feature imports GitHub service credentials only. Codex/Claude agent authentication remains managed by those applications. Wrangler OAuth and remote MCP OAuth remain separate, unsupported import types.

## Portainer read-only MCP (0.4.0)

Update the plugin; its bundled helper is installed automatically. Custom helper locations still need manual updates. Add an account with service **Portainer**, a name, a connection ID, and its server origin (for example `http://portainer-host.example.ts.net:9000`). Paste an access token from Portainer **My account → Access tokens** into the plugin's local token field and save. Tokens stay in Windows Credential Manager. **Verify account** checks the authenticated environments endpoint and reports the number accessible to the token; it does not claim to identify its owner.

The URL accepts HTTP or HTTPS origins with optional ports. Paths, queries, fragments and embedded credentials are rejected. HTTPS validates certificates. HTTP can be used with a trusted private network such as Tailscale; the machine running the helper must be connected to that network. Changing the destination URL requires entering the token again. Redirects are never followed with the credential.

Choose **Connect a tool or agent → Portainer: built-in read-only MCP**, select the account, use the shared helper, and generate Claude or Codex configuration. Merge the individual definition into the agent's MCP settings (or use MCP Manager's advanced editor) and restart the agent/server. No additional MCP package or Portainer-side installation is needed. Do not overwrite other MCP entries. Each account should use a distinct server name if you add more than one.

The helper command is:

```powershell
& "$env:LOCALAPPDATA\ECPA\helpers\connections-manager\ecpa-connect.exe" portainer-mcp portainer-demo
```

It serves newline-delimited JSON-RPC over stdin/stdout and is meant to be launched by an MCP client. Use `--data-dir PATH` before the command if the plugin uses a custom catalogue location. It reads the selected credential from the vault for each tool call, without passing it through command arguments or config. The same user and catalogue can serve Codex and Claude. Project assignment and generic `run` credential export are not supported for Portainer; use the built-in MCP preset directly.

Tools:
- `portainer_environments`: accessible environment IDs, names, types and status.
- `portainer_stacks`: stack metadata, excluding compose files, Git credentials and environment variables.
- `portainer_containers`: Docker/Swarm container IDs, names, image and status for an explicit environment ID. Kubernetes containers are not supported.
- `portainer_logs`: up to 200 recent lines for a hexadecimal container ID; no streaming/follow mode.

Only these GET routes are implemented. There is no arbitrary HTTP proxy, deployment, restart, exec, deletion or stack-content tool. Response size is bounded at 2 MiB; lists return up to 500 items and mark truncation. Docker log framing is decoded and the connection token is redacted, but application logs can contain other secrets. Returned content is untrusted data.

Validated with synthetic Portainer responses, the actual core, native helper, Windows vault and browser. Reachability of Portainer 2.45.2 was checked separately; real authenticated instance access still requires the user's token. The implementation targets Portainer's `/api/endpoints`, `/api/stacks` and Docker proxy routes. Permission failures and incompatible environment types are returned as tool errors.

## Guided setup and shared helper (0.5.0)

New connections use four steps: **Service → Connection method → Account details → Review and connect**. GitHub offers existing CLI login, browser sign-in and tokens; Cloudflare and Portainer offer their supported token method. Back preserves your draft. Token fields and service-specific fields only appear when relevant. Existing accounts open directly for editing. Save first, then verify access and connect a tool.

Version 0.6.0 supersedes the manual helper setup from 0.5.x: Settings defaults to the bundled, managed helper. One executable serves all connections and agents. Advanced custom locations remain browser-local. **Verify helper** checks the executable/version with a three-second deadline; **Verify account** checks service access. Neither automatically registers an MCP server in an agent.

The tool generator filters choices by selected account or project. Portainer exposes only the built-in MCP and Codex/Claude formats. GitHub and Cloudflare expose matching CLI presets and advanced local MCP/custom executable options. CLI commands offer PowerShell output only. Changing accounts clears stale generated commands.

Service logos are bundled from [Simple Icons](https://github.com/simple-icons/simple-icons), distributed under CC0-1.0. Brand marks remain the property of their respective owners. No external image requests are needed.

## Windows path separators (0.5.2)

The helper and plugin now use the same credential namespace for Windows paths spelled with `\` or `/`. Previously, a forward-slash `--data-dir` could load the catalogue but report its saved token missing. New writes use the backslash namespace; reads also check the old forward-slash namespace and the exact supplied spelling. Existing backslash/forward-slash credentials need no manual migration. Existing legacy entries are updated together on token replacement and removed together on deletion. Conflicting tokens under those spellings are rejected until you explicitly re-save the intended token.

Update the plugin (and any manually maintained custom helper). All credential readers (status, verification, process launcher and Portainer MCP) share this lookup. No tokens are printed or copied into the catalogue. This fix normalizes separator style only: keep directory casing, trailing separators and junction/alias spelling consistent with the original configuration. A legacy mixed-separator entry is found when its exact original spelling is supplied; resaving through that spelling also creates the normalized entry. Moving the catalogue still does not transfer credentials.

## Building the bundled helper

Use `python scripts/package.py --plugin connections-manager` for installation artifacts and real-core tests. Packaging builds the helper without an embedded payload, verifies its reported version, then builds the DLL with the `bundled-helper` feature and that exact executable embedded. The plugin ZIP still contains exactly one DLL, compatible with existing ECPA plugin installers. No third-party worker, extension, cookie collector or runtime downloader is included.

A plain `cargo build` is a development build without a bundled helper; the editor labels it and offers the custom-helper workflow. Do not distribute a plain-build DLL as the managed release. The managed helper is intentionally retained on uninstall so existing agent configurations do not become broken; remove it manually after disconnecting those agents if no longer needed.


## Managed MCP gateway (0.7.0)

The existing Accounts & CLI page now links to **MCP services & gateway**. A separate
Python SDK worker supplies authenticated Streamable HTTP, named account profiles,
Bitwarden Secrets Manager references, explicit client/project/tool grants, activity,
OAuth drafts, client setup previews/backups and rollback. The native Portainer
implementation is reused through an isolated environment mode.

Install/configure the separate worker before opening this page; it is not bundled
as an invisible downloader in the DLL. See [runtime architecture and setup](../../runtime/mcp-gateway/README.md)
and [Windows host readiness](../../runtime/mcp-gateway/HOST-READINESS.md). The plugin
reads gateway-runtime.json in its configured data directory and forwards only to
a loopback worker using the same Windows identity's vault. Existing connection
records/credentials are retained.

A real Bitwarden-backed Portainer read through the authenticated gateway has now
passed on the development PC. The final Windows central host, Tailscale TLS endpoint,
reboot persistence and real service-specific OAuth/Runway/provider verification
remain deployment checks. The gateway worker is a separate release asset; follow its host setup guide.

## Shared services and providers (0.8.0)

Gateway 0.2.0 adds built-in Cloudflare account reads, Runway balance/task reads,
saved SSH machines and Bitwarden-backed model API keys. The guided setup shows
only relevant fields. Optional Wrangler jobs, SSH restarts and paid video requests
need explicit per-request approval in **Operation approvals**. Provider profiles
publish named model aliases through CLIProxyAPI; core authentication applies,
separately from MCP client/project permissions. Existing native OAuth profiles stay
with the core. No new global account switch is introduced.

Update both the plugin and gateway bundle for these features; the DLL does not
silently replace a running Python worker. See the [0.2 upgrade procedure](../../runtime/mcp-gateway/HOST-READINESS.md#upgrade-from-01-to-02)
and [runtime contracts and limitations](../../runtime/mcp-gateway/README.md).

## Remembered management login (0.8.1)

Accounts & CLI and Shared services & providers reuse the workspace plugins' saved
management key on the same proxy origin. Select **Remember key on this device**
after a successful login to persist it; leave it unchecked to use tab-scoped session
storage. Moving between the two pages or reopening their iframe no longer requires
retyping the key when the saved browser storage is available.

This is browser storage, not ECPA desktop single sign-on or an encrypted vault.
Other pages on the same origin can access it. Only trusted plugins should share
that origin. **Lock & forget** removes the shared remembered key and the Connections
tab key; already-unlocked pages remain authenticated until closed/locked. A rejected
key is removed automatically. Network failures keep it for retry, and disabled
browser storage falls back to manually entering the key. Account/provider credentials
are unaffected. Gateway 0.2.0 needs no reinstall for this UI patch.
