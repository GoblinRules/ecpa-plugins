# Z.ai Provider

Windows amd64, version 1.1.0. A maintained MIT adaptation of cr1cr1/cpa-auth-zai; see [UPSTREAM.md](UPSTREAM.md).

## Default setup: an existing API key

Install through the ECPA Plugins registry and open **Z.ai Provider**. Supply the proxy management key, a stable connection ID, a display name and an existing **Coding Plan** API key created in Z.ai’s official dashboard. Confirm you checked its account/organisation and billing classification. Review the connection, then explicitly save it.

The plugin does not create, rotate or delete API keys. Review does not contact Z.ai or persist the key. Pending reviews expire after ten minutes. Saved keys enter ECPA’s native credential store, **not Windows Credential Manager**. The display name is your label, not an independently verified identity. Existing IDs cannot be overwritten through this page. Manage/revoke credentials through ECPA and the provider dashboard as appropriate.

Inference retains upstream Chat Completions, Responses and Anthropic Messages routing. Model discovery uses the saved key. There is no invented model fallback, prompt injection, ZCode impersonation or token fallback for inference. Errors remain explicit if the provider rejects a key, model or protocol. A saved key alone does not prove live access or billing classification.

## Optional experimental browser login

Disabled by default. The login and key-management APIs are undocumented integration contracts. To explicitly enable them, configure all of:

```yaml
enable-browser-login: true
expected-account: person@example.com
organization-id: YOUR_ORGANISATION_ID
project-id: YOUR_PROJECT_ID
api-key-name: YOUR_UNIQUE_EXISTING_KEY_NAME
billing-confirmed: true
```

Never put a token or API-key secret in plugin configuration. The returned email/user ID must match `expected-account`. The specified organisation and project must exist in the account. The plugin reads only the exact existing key name, rejecting missing or duplicate matches. There are **no key-creation calls**. It never picks a default organisation or first project. Reconfiguration invalidates pending flows. Each flow snapshots the intended account and selection.

Login-derived business credentials support the inherited quota/usage features. API-key-only connections may not support those monitor endpoints; unavailable quota remains unknown. Browser-login credentials require a new sign-in when expired; no refresh mechanism is claimed. Do not enable this workflow until you have independently checked that key’s billing classification. The plugin cannot determine whether an existing key is Standard or Coding Plan billed.

## Privacy and compatibility

Requests go only to `api.z.ai` and (for explicitly enabled login) `zcode.z.ai`, using verified HTTPS and rejecting redirects. Inference sends the selected API key and a truthful plugin User-Agent. No ZCode token, OS version, timezone, device/session fingerprint or spoofed client headers are attached to inference. Malformed-stream logs include only byte counts; upstream error bodies are not echoed to clients or logs. Explicit usage-history timezone parameters remain part of the usage feature.

The independent Go HTTP transport avoids core HTTP-body logging and redirect behaviour. Standard HTTP_PROXY/HTTPS_PROXY/NO_PROXY environment settings apply; ECPA’s per-account proxy settings do not.

The provider ID remains `zai`. Do not enable this alongside upstream cpa-auth-zai or another provider/executor named zai. This plugin ID is `zai-provider`, with its own release repository. Existing upstream auth files are not migrated or edited automatically.

Tested against CLIProxyAPI 8.0.52 with synthetic credentials and a compile-time fixture transport. **No live Z.ai login, inference, quota, billing or approved-tool eligibility has been verified for this adaptation.** Removing upstream client impersonation may cause unsupported endpoints to reject requests; the plugin will surface that failure rather than spoof a client or silently fall back to another billing route.

## Build and tests

See [Go plugin build instructions](../../docs/go-plugins.md). `python scripts/package.py --plugin zai-provider` creates the release ZIP. `go test -mod=vendor ./...` covers protocol forwarding, authentication selection, no-create behaviour, private errors/logs, confirmation and destination restrictions. Dependencies are vendored and release builds run offline. [SECURITY.md](SECURITY.md) records remaining limits.
