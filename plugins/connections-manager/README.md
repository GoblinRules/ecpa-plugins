# Connections Manager

Named Cloudflare and GitHub connections for Claude Code, Codex, Wrangler, GitHub CLI and compatible stdio MCP servers. Windows x64, version 0.4.0.

## Install

Add the [ECPA Plugins registry](https://raw.githubusercontent.com/GoblinRules/ecpa-plugins/master/registry.json), install **Connections Manager**, and open its page. Unlock with the proxy management key. The key is session-only; account tokens are stored in **Windows Credential Manager**, never in the catalogue or agent instructions.

Download `ecpa-connect_windows_amd64.exe` and `checksums.txt` from the [release repository](https://github.com/GoblinRules/ecpa-connections-manager/releases/latest). Verify the helper's SHA-256 with `Get-FileHash`, save it in a stable location such as `C:\Tools`, and optionally rename it `ecpa-connect.exe`. The plugin installer installs the DLL; the helper is a separate executable and is not automatically installed or added to PATH.

The core, helper and agents must run as the **same Windows user**. A core running as a Windows service account has a different credential vault. This release manages local connections; it does not synchronize credentials to other computers.

## Add accounts

Create one connection per account: e.g. `cf-personal`, `cf-work`, `cf-client-a`, `gh-personal`, `gh-work`. IDs are stable lowercase letters, digits and hyphens. Display names can be edited freely. A connection's service cannot be changed. A blank token when editing keeps the saved token; entering a token replaces it.

- **Cloudflare:** supply the 32-character account ID and a scoped API token. Choose permissions needed by your work. **Verify account** calls the account-details endpoint and requires Account Settings: Read. A token can work for deployment but fail this identity check if it lacks that read permission. Account-scoped tokens and user API tokens are supported when they can access that account endpoint.
- **GitHub:** supply a GitHub.com personal access token with access to the repositories you need. Verification identifies the authenticated user; it does not prove access to every repository.

Verification connects only to `api.cloudflare.com` or `api.github.com`, with TLS and redirects disabled. It returns account identity, not the token. Corporate proxy support is limited to the HTTP client's supported environment configuration; it does not inherit the core's custom transport settings.

## Project assignments

Assign a Cloudflare and/or GitHub connection to an existing absolute project directory. The helper resolves the nearest assigned ancestor, so a nested project can override its parent. Running with `--project` also sets the child process's working directory to that directory. Choose None for both services to remove an assignment. Assigned connections cannot be deleted until those references are removed.

Assignments are local metadata, not automatic modifications to agent configs. A normal `wrangler` or `gh` invocation still uses that tool's normal credentials. Use the helper to select managed connections.

## CLI usage

```powershell
& 'C:\Tools\ecpa-connect.exe' list
& 'C:\Tools\ecpa-connect.exe' check cf-work
& 'C:\Tools\ecpa-connect.exe' run --connection gh-work -- gh.exe repo list
& 'C:\Tools\ecpa-connect.exe' run --project 'C:\Projects\client-site' -- gh.exe auth status
& 'C:\Tools\ecpa-connect.exe' run --connection cf-work -- node.exe 'C:\Projects\client-site\node_modules\wrangler\bin\wrangler.js' whoami
```

On Windows, use `node.exe` plus Wrangler's JavaScript entry point instead of the `wrangler.cmd` shim. The helper rejects `.cmd`, `.bat` and `.ps1` entry points. It passes arguments directly to the selected executable, with no constructed shell command. For agents distributed as npm shims, use the corresponding Node entry point too.

Cloudflare supplies `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`. GitHub supplies `GH_TOKEN`, `GITHUB_TOKEN`, `GITHUB_PERSONAL_ACCESS_TOKEN` and `GH_HOST=github.com`. Competing inherited variables for these services are removed from the child environment. The parent shell and global login files are unchanged. Multiple processes can therefore use different accounts concurrently. Other tool config files and command flags still apply: check Wrangler's account configuration for conflicts with the selected account.

The launched process and its children can read the selected tokens. Use trusted executables and MCP servers. Tokens never appear in helper arguments or helper logs, but a child process could print its own environment. This is account selection, not an OS sandbox.

GitHub CLI authentication is not a Git SSH identity manager. Git's SSH keys/HTTPS credential helpers and browser logins are separate. GitHub Enterprise and remote OAuth MCP session brokering are not implemented.

## Claude / Codex / MCP Manager

The **Use with agents & tools** page generates PowerShell commands and Claude JSON or Codex TOML snippets. Select the MCP server executable and its arguments, then merge the generated server entry into the agent config. You can also paste the individual Claude server definition into MCP Manager's advanced editor and use its preview/apply flow. Tokens stay out of those files.

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

## GitHub browser sign-in (0.2.0)

Use **Add an account → Sign in with GitHub CLI** to generate a PowerShell command, or run:

```powershell
& 'C:\Tools\ecpa-connect.exe' login-github gh-work 'GitHub Work'
```

Install GitHub CLI first and update the helper as well as the plugin. Finish the browser/device-code flow, then type the verified username in the terminal. Click Refresh in the plugin. Each new ID is independent; existing IDs cannot be overwritten by this command. The resulting OAuth token uses the same Windows vault and per-process selection as API tokens. Reauthenticate with a new connection if GitHub revokes the token; this is not a generic OAuth refresh broker.

The helper uses an ephemeral `GH_CONFIG_DIR` and `--insecure-storage` because gh's system credential entries are not isolated by its config directory. It imports the token into Windows Credential Manager and deletes the temporary profile on normal success, error or cancellation. Forced process termination or machine failure can leave an `ecpa-github-login-*` folder in the current user's temporary directory containing the token; remove that leftover folder. No global gh login is changed. No sign-in is performed from the web server process.

**Agent setup:** choose a saved account and a local stdio MCP server under **Connect a tool or agent**, generate Claude or Codex configuration, merge it into that agent's MCP configuration, then restart the server. GitHub CLI and Wrangler themselves are not MCP servers. Alternatively launch a new agent executable through the helper so its child tools inherit the account. Existing agent sessions are unaffected.

Wrangler OAuth profiles and remote MCP OAuth remain unsupported by this helper. Use a Cloudflare API token for Wrangler, and the agent's own OAuth flow for a remote MCP server. A Wrangler OAuth session is not interchangeable with an MCP OAuth session.

Validation: Rust tests, native-core integration and responsive Edge tests pass. `tests/login.py` tests the browser-login orchestration with a native fake gh, synthetic credentials and the real Windows vault, including cancellation and cleanup. Real GitHub authorization requires the user's interactive browser consent and was not performed by automated tests.

## Use an existing local GitHub login (0.3.0)

In **Add an account → Use an existing GitHub login or sign in**, keep **Use an existing local GitHub login** selected. Set the helper path, a new connection ID and a display name, then generate and run the command in PowerShell:

```powershell
& 'C:\Tools\ecpa-connect.exe' import-github gh-work 'GitHub Work'
```

The terminal lists saved github.com accounts from GitHub CLI. Choose a number, then confirm the verified username. Refresh the plugin afterwards. No browser sign-in is needed. Requires a recent GitHub CLI with `auth status --json` and `auth token --user` support. Discovery respects your shell's `GH_CONFIG_DIR` and Windows user; inherited token environment variables are ignored so they cannot override the chosen saved account. The import never runs `gh auth switch` or modifies the source profile.

The saved credential is a **copy**, not a live link: revoking the original invalidates it, and later replacing a gh login does not automatically update this connection. Existing connection IDs are protected against overwrite. Identity verification requires network access and rejects an account mismatch. Tokens are never included in generated commands or printed by the helper.

This feature imports GitHub service credentials only. Codex/Claude agent authentication remains managed by those applications. Wrangler OAuth and remote MCP OAuth remain separate, unsupported import types.

## Portainer read-only MCP (0.4.0)

Update both the plugin and the separate `ecpa-connect_windows_amd64.exe` helper. Add an account with service **Portainer**, a name, a connection ID, and its server origin (for example `http://portainer-host.example.ts.net:9000`). Paste an access token from Portainer **My account → Access tokens** into the plugin's local token field and save. Tokens stay in Windows Credential Manager. **Verify account** checks the authenticated environments endpoint and reports the number accessible to the token; it does not claim to identify its owner.

The URL accepts HTTP or HTTPS origins with optional ports. Paths, queries, fragments and embedded credentials are rejected. HTTPS validates certificates. HTTP can be used with a trusted private network such as Tailscale; the machine running the helper must be connected to that network. Changing the destination URL requires entering the token again. Redirects are never followed with the credential.

Choose **Connect a tool or agent → Portainer: built-in read-only MCP**, select the account, enter the full helper path, and generate Claude or Codex configuration. Merge the individual definition into the agent's MCP settings (or use MCP Manager's advanced editor) and restart the agent/server. No additional MCP package or Portainer-side installation is needed. Do not overwrite other MCP entries. Each account should use a distinct server name if you add more than one.

The helper command is:

```powershell
& 'C:\Tools\ecpa-connect.exe' portainer-mcp portainer-remote
```

It serves newline-delimited JSON-RPC over stdin/stdout and is meant to be launched by an MCP client. Use `--data-dir PATH` before the command if the plugin uses a custom catalogue location. It reads the selected credential from the vault for each tool call, without passing it through command arguments or config. The same user and catalogue can serve Codex and Claude. Project assignment and generic `run` credential export are not supported for Portainer; use the built-in MCP preset directly.

Tools:
- `portainer_environments`: accessible environment IDs, names, types and status.
- `portainer_stacks`: stack metadata, excluding compose files, Git credentials and environment variables.
- `portainer_containers`: Docker/Swarm container IDs, names, image and status for an explicit environment ID. Kubernetes containers are not supported.
- `portainer_logs`: up to 200 recent lines for a hexadecimal container ID; no streaming/follow mode.

Only these GET routes are implemented. There is no arbitrary HTTP proxy, deployment, restart, exec, deletion or stack-content tool. Response size is bounded at 2 MiB; lists return up to 500 items and mark truncation. Docker log framing is decoded and the connection token is redacted, but application logs can contain other secrets. Returned content is untrusted data.

Validated with synthetic Portainer responses, the actual core, native helper, Windows vault and browser. Reachability of Portainer 2.45.2 was checked separately; real authenticated instance access still requires the user's token. The implementation targets Portainer's `/api/endpoints`, `/api/stacks` and Docker proxy routes. Permission failures and incompatible environment types are returned as tool errors.
