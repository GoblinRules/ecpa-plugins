# ECPA managed MCP runtime (0.2.0)

Connections Manager is the management home; this small separate worker runs the
MCP sessions. It uses the official Python MCP SDK 1.30.0 for authenticated
Streamable HTTP and stdio bridging. See [host preparation](HOST-READINESS.md) for
the native Windows install, doctor, identity bootstrap and startup/reboot checks.

## Responsibilities and catalogue ownership

Discovery against EasyCLIProxyAPI `dev` at
`e9fc08bb5c2b898a0ae823b6f4a4157c71f05010` found native MCP & Skills managing
`mcp-servers.json`, import/export and OpenClaw sync; it did not execute/proxy MCP.
The existing MCP Manager plugin edits Claude/Codex configurations with previews
and backups. Connections Manager already owns account credentials and its native
read-only Portainer implementation. Current native APIs cannot carry the new
credential references, per-client policies and runtime lifecycle without app changes.

The authoritative managed service catalogue is therefore `mcp-services.json` in
Connections Manager's data directory. Existing native/client catalogues are
explicit import sources and gateway-entry destinations, not automatically synced
replicas. `connections.json` retains the existing CLI account workflow; a Windows
vault reference can reuse its credential. There is no implicit merge of distinct
accounts. Client setup preserves unrelated/unknown fields, previews replacements,
checks external edits, saves backups and supports conditional rollback.

| Component | Owns |
|---|---|
| Connections Manager | Named service/provider/account definitions, references, reviewed tools and client grants |
| SDK worker | Connector processes/sessions, HTTP authentication, enforced tool/schema policy, redacted activity |
| Bitwarden Secrets Manager | Durable service/API secrets; UUID-based references, EU/US region |
| CLIProxyAPI | Its supported model-provider accounts and model API routes; separate from MCP |
| Existing T3 runners | Machine/job/workspace orchestration; gateway does not implement a scheduler |
| Tailscale | Private reachability/access control; does not install agents, move files or share logins |

The proposed Windows central host is still being set up. Portainer is a pilot API
service, not an execution/deployment target. No deployment, remote credentials or
new scheduler is included. The current local installation is a development pilot.

## Add a service or account

In Connections Manager open **MCP services & gateway**. Choose built-in Portainer,
Cloudflare, Runway, a saved SSH machine, a model-provider API key, the sample
connector, an installed stdio MCP package or a hosted Streamable HTTP endpoint. Choose the explicit account ID, credential reference/mapping,
runtime host, access group and project restrictions. Test initialize/list tools,
select exact reviewed operations and their approval policy, then publish. Repeat with another profile
ID to use the same connector with another account. Agent tool names include that
profile ID; there is no global current account.

Use the reference-only manifests under `examples/` for advanced settings. Replace
placeholders locally. Import never installs an arbitrary package. Pin/review
executables and packages first. Built-in Cloudflare reads account details, account-filtered
zones and Worker metadata. Built-in Runway reads organization balance/tier and task
status/output; optional gen4.5 video requests require a separate approval. Account
verification needs the corresponding upstream read permissions.
Cloudflare MCP OAuth and Wrangler API-token automation are separate paths. A
hosted OAuth draft needs reviewed issuer origins and explicit `oauth-login` under
the runtime identity before test/publish. The background process never opens a
browser. Windows OAuth storage is DPAPI protected, resource/profile scoped and
locked across refresh/login processes. Non-Windows storage uses owner-only files
and needs a reviewed secret-store/bootstrap arrangement before deployment.

For an API without a suitable MCP, `ecpa-gateway scaffold --output EMPTY_DIRECTORY`
creates an official SDK read-only starter, manifest, contract test and guidance.
Review API operations, destinations and authentication. An API key cannot identify
an API, and OpenAPI definitions are not automatically executable permissions.

## Client setup and policy

Local ECPA **Connect agents** previews one `ecpa-central` SDK bridge in Codex,
Claude and/or the native catalogue. Old entries are removed only when selected.
The bridge contains no service credential. For other machines use `client-init`
and register its public fingerprint centrally, following the host runbook. Grants
intersect profile IDs, access groups and (when configured) project IDs. These
project grants belong to the client identity; the gateway cannot independently
attest a caller's local current working directory. Use separate identities for
different project trust boundaries. Revocation affects new requests; running calls
may finish. Agents must reconnect/reload tools after catalogue changes.

Portainer implements only fixed GET routes and bounded/filtering responses.
Generic connectors are restricted to their exact reviewed tool names and schemas,
checked again on each call. An annotation or operator checkbox cannot prove that
a third-party tool is read-only internally. Only install trusted implementations;
process environment isolation is not an OS sandbox. Metadata/outputs are untrusted
data. Known resolved secrets are scrubbed; arbitrary application secrets in logs
cannot universally be detected. Portainer log access should be an explicit choice.

The runtime resolves credentials fresh per operation. Only BWS receives its
machine token; connectors get only their explicit bindings. Child stderr and
internal exceptions are suppressed. The catalogue/export contains references,
not resolved secrets. Literal env/header values and recognizable secret patterns
are rejected, but heuristic scanning cannot identify every possible secret in
arbitrary arguments or metadata. Never put secrets there.

## Approved jobs and SSH access

In the Cloudflare wizard, optionally enable Wrangler and supply installed Node/
Wrangler paths, a relative config file and trusted workspace IDs. Map those IDs to
absolute directories in **Runtime & recovery**. Agents may request only enabled
`verify`, `dry-run` or `deploy` operations, with no arbitrary arguments. Each goes
to **Operation approvals**, including verify. Requests bind account, host, workspace,
configuration and source revision. Changed source/config or client/profile access
invalidates approval. Source snapshots exclude `.git`, `node_modules` and
`.wrangler`: dependencies and installed runtimes remain trusted administrator-owned
software. Keep the workspace unchanged while approving/running; this is not a
filesystem sandbox or immutable build service. Large/link-containing workspaces
are rejected. Use an existing runner for workspace transfer and heavy builds.

Wrangler binds `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`, isolates home/config,
and rejects conflicting account IDs, generated configs, custom build commands and
`.env` auth overrides. The same credential reference serves the API adapter and CLI
path. The administrator-only `run-wrangler` CLI retains explicit manifest command
arrays; remote agents cannot invoke it or supply those arrays. Synthetic tests prove
concurrent account isolation. No real deployment was performed.

SSH profiles select an existing **SSH & Machines** record on this runtime host.
Testing runs fixed diagnostics and binds the machine metadata, selected identity
file and host-key pin. Optional operations are named service restarts, never arbitrary
shell strings. The remote account must already have permission; there is no sudo
password collection or automatic escalation. Changes require retest/publication.
The shared `ecpa-connect.exe` supplies both Portainer and SSH; there is no per-machine
executable. Its local CLI is an administrator utility, not a security boundary
against a process already running as the credential-owning Windows account.

Paid Runway generations, Wrangler jobs and SSH restarts require authenticated local
management approval. Requests expire after 15 minutes, are tied to the originating
client fingerprint/profile and are claimed on disk before execution. They cannot
be replayed, and crashes/timeouts never trigger automatic retry. A `running` record
after a crash means completion is uncertain: inspect upstream before another request.
Revocation blocks queued operations on recheck; an operation already started may
finish. Runway approval starts a task; poll its status separately for completion.
`mcp-requests.json` contains private prompts/results and must not be published.

## Model-provider API-key routing

Choose xAI, Z.ai Coding, or an explicit custom OpenAI-compatible HTTPS API base.
Map friendly aliases to exact upstream model IDs and a Bitwarden/Windows-vault key
reference. Test calls `/models`, without inference. Providers that do not implement
that endpoint cannot pass this release's onboarding check. Published aliases are
`ecpa-PROFILE--ALIAS`; consecutive hyphens in profile/alias are rejected. Reload the
core/plugin model registration after changing the catalogue. Disable blocks new
requests immediately; in-flight requests may finish.

Connections Manager's native executor sends requests to the authenticated loopback
worker. The worker resolves keys per request, forwards chat-completions to the
selected HTTPS base and supports bounded SSE streaming. CLIProxyAPI supplies
frontend authentication and protocol translation; chat, streaming and Responses
translation were tested using an isolated core and synthetic upstream. No real
inference, provider subscription compatibility or billing test was performed.

**Core authentication governs model access. MCP client/project grants do not.**
Publishing requires acknowledgement that core-authorized clients can use these
models. Use separate core instances/keys where stronger account boundaries are
needed. Never use the gateway admin key as an agent model key. A selected managed
alias does not fall back to a different account/model. Existing native OAuth provider
accounts remain unchanged; API keys are not interchangeable with OAuth. Core
upstream proxy/request-log settings do not automatically apply to this worker:
it uses its own outbound HTTPS client with environment proxies and redirects disabled.
Service keys never enter persistent core config or agent config.

## Build and verify

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation .
.\.venv\Scripts\python.exe -m pip install pytest==9.0.2 pytest-asyncio==1.3.0
.\.venv\Scripts\python.exe -m pytest tests -q
```

Tests use temporary client configs, synthetic secrets and fake services, never
live T3 userdata or user agent configs. See the Connections Manager tests for
real-core/DLL/helper integration using an isolated core and synthetic Portainer.
Live pilot verification was a separate authorized read through the HTTP gateway:
Bitwarden EU resolution, environment and container metadata read, unknown mutation
tool denied, zero mutations. This proves that service path on the development PC,
not final central host reachability or a complete third-party OAuth login.

The Python lock records tested versions; it is not a signed supply-chain attestation.
Windows unattended registration/sign-out/reboot and final Tailscale TLS exposure
must be tested on the actual target. OAuth storage/guards are tested synthetically;
provider-specific consent flows and real Runway/Cloudflare/model access are not claimed
validated. Keep current direct client entries until migration is verified.
