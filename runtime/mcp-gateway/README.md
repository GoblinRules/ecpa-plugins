# ECPA managed MCP runtime (0.1.0)

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
| Connections Manager | Named MCP service/account definitions, references, reviewed tools and client grants |
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
the sample connector, an already installed stdio MCP package or a hosted Streamable
HTTP endpoint. Choose the explicit account ID, credential reference/mapping,
runtime host, access group and project restrictions. Test initialize/list tools,
select exact reviewed read-only tools, then publish. Repeat with another profile
ID to use the same connector with another account. Agent tool names include that
profile ID; there is no global current account.

Use the reference-only manifests under `examples/` for advanced settings. Replace
placeholders locally. Import never installs an arbitrary package. Pin/review
executables and packages first. Runway uses an appropriate separately installed
MCP/hosted adapter; merely choosing its service label does not implement its API.
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

## Wrangler and provider routing status

`run-wrangler --profile ID --workspace ID --operation verify` executes on this
runtime host only. Configure explicit installed Node/Wrangler paths, trusted
workspace IDs and approved operation argument arrays in the manifest/runtime.
It binds `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`, clears competing auth,
uses isolated home/config paths and rejects conflicting account IDs, generated
configs, custom build commands and `.env` auth overrides. Synthetic tests cover
concurrent profiles. No real Cloudflare deployment has been performed. A local
job still runs trusted workspace/package code with its scoped token; it is not
a sandbox. Jobs on other workers require a trusted runner and workspace transfer.

CLIProxyAPI provider API-key/OAuth routing remains its own integration. The
Bitwarden reference resolver is reusable, but this release does **not** inject
Bitwarden keys into CLIProxyAPI provider config or claim native secret-reference
support. That adapter remains required. Copying resolved keys into its persistent
config would create a second plaintext store, so it is not done silently. Existing
provider accounts/routing remain unchanged. There is no fabricated model MCP.

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
provider-specific consent flows and real Runway/Cloudflare access are not claimed
validated. Keep current direct client entries until migration is verified.
