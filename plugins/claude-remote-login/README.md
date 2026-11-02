# Claude Remote Login

Windows amd64, version 1.1.0. A maintained MIT adaptation of Yousha-dev/claude-remote-login; see [UPSTREAM.md](UPSTREAM.md).

## Use

Install from the ECPA Plugins registry and open **Claude Remote Login**. Enter the proxy management key, generate a link, and complete Claude sign-in on the account owner’s device. Paste the returned `code#state`, then click **Review account**. This exchanges the code but does **not** save the account. Review the email and organisation, check the consent box, then **Confirm and save**.

Confirmation adds the account to ECPA’s normal Claude inference pool. It does not log other CLIs into third-party services. Access and refresh tokens are held by ECPA’s native credential store, **not Windows Credential Manager**. Anyone allowed to use the proxy’s Claude pool may use this account according to ECPA routing/access settings.

The login session is memory-only, expires after 15 minutes and can be cancelled. The management key is not persisted in browser storage. PKCE binds the code to this exact login attempt. Failed saves can be retried without exchanging the code again. A proxy restart discards pending sessions.

Reauthorising an existing native filename preserves its routing settings and device identity. Listing/reading failures, malformed records, identity mismatches and changes since review stop the save. Review again after a conflict. Coordinate account edits: ECPA’s host API does not provide an atomic compare-and-save transaction across independent clients.

## Network and compatibility

Only fixed HTTPS token/profile endpoints at `platform.claude.com` and `api.anthropic.com` are used by the plugin. Browser authorisation uses `claude.com`. Redirects are rejected; TLS verification stays enabled. Requests use an independent Go HTTP client to avoid core request/response logging and redirect behaviour. Standard HTTP_PROXY/HTTPS_PROXY/NO_PROXY environment settings apply; ECPA’s per-account proxy settings do not.

Tested with CLIProxyAPI 8.0.52 on Windows amd64 using synthetic credentials and a compile-time test transport. Live Claude login/SSO and subscription eligibility have **not** been verified in this adaptation. Provider endpoints/client permissions can change. This is not an Anthropic-endorsed integration.

## Build and tests

See [Go plugin build instructions](../../docs/go-plugins.md). `python scripts/package.py --plugin claude-remote-login` creates the release ZIP. `go test ./...` covers PKCE, state/expiry, confirmation, retries, preservation conflicts, redirect blocking and response limits. `tests/provider_plugins.py --core <path>` exercises fixture DLLs with an isolated real core; no personal credentials are used.

See [SECURITY.md](SECURITY.md) for review scope and remaining limits.
