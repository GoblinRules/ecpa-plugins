# Provider plugin security review — 2026-11-02

Scope: maintained source adaptations of Claude Remote Login and Z.ai Provider at the revisions recorded in each plugin’s UPSTREAM.md. This review does not certify the proxy core, operating system, toolchains, future upstream revisions or provider policy compliance.

## Findings addressed

- Claude account imports now exchange the code into a temporary review, then require explicit identity confirmation before saving. Failed listing/reading, malformed records, identity mismatch and edits since review stop the save. Existing routing, disabled state and device identity are preserved.
- Z.ai no longer creates API keys or selects the default organisation/first project. The default setup imports an existing key with review and confirmation. Optional experimental browser login requires an expected identity, explicit organisation/project/key name and billing acknowledgement.
- Removed ZCode client impersonation, shell-based OS discovery and fingerprint headers. Inference forwards caller prompts without adding system/developer instructions.
- Removed response bodies and parsing snippets from malformed-stream logs and provider error details.
- Provider HTTPS uses verified TLS, explicit destinations, rejected redirects, limits and timeouts. The independent transport avoids the core HTTP bridge’s redirect/body-logging behaviour.
- Sensitive management operations remain behind ECPA authentication. Pages use no browser credential storage or external scripts. Pending credentials expire and are cleared on cancellation/shutdown.
- Releases build pinned source offline after checksum-verified toolchain installation. Dependency/upstream notices accompany the binary. Test transports use a separate build tag and output directory; packaging rejects that tag and requires ASLR on release DLLs.

## Validation

Go tests include the race detector and vet, redirect rejection, no-create behaviour, prompt forwarding, account/organisation selection, consent, preservation conflicts and private errors. Release tooling tests cover independent versions, checksums, native builds and notices. Isolated CLIProxyAPI 8.0.52 tests use temporary credential directories and synthetic accounts; no production ECPA configuration or credentials are touched. Native model discovery, non-streaming/streaming inference, account review/save, duplicate rejection and production DLL loading passed. Browser checks passed for consent, secret-input clearing, responsive layouts and the iframe CSP under a simulated Tauri origin. This is not an end-to-end WebView2 app test; the browser harness disables Edge’s local-network access check for its routed synthetic parent origin, while preserving CSP enforcement.

## Remaining limits

No malicious LLM instruction or deliberate credential-stealing behaviour was identified in the reviewed runtime source. That is a review finding, not proof that software cannot contain defects. Remote model output remains untrusted.

Live OAuth, provider inference, quota endpoints, billing classification and approved-client eligibility have not been verified. Z.ai’s undocumented login may reject these truthful client headers. Failures are surfaced; impersonation is not restored. Both plugins save through ECPA’s native credential store, not Windows Credential Manager. Native DLLs have the proxy process’s privileges. ECPA’s save API has no cross-client atomic compare-and-save operation.

Standard HTTPS_PROXY/HTTP_PROXY/NO_PROXY environment settings apply; ECPA per-account proxy settings do not apply to the private transport. The account owner must understand that saved accounts become usable through the proxy under its existing routing/access rules.
