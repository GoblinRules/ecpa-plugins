# Security scope

This adaptation is not a safety certification. Native DLLs execute with the proxy process’s privileges, without a plugin sandbox. Install only source/builds you trust and protect the proxy management key and native credential directory. Use HTTPS or a trusted encrypted network when opening management pages remotely.

## Implemented controls

- Pinned upstream source and preserved MIT notices; no upstream release binary reused.
- Explicit review/confirmation before the default setup saves credentials.
- No browser credential persistence, external scripts, telemetry collector or LLM instructions embedded in runtime assets.
- Fixed HTTPS destinations, TLS verification, redirects rejected, bounded non-streaming responses and timeouts.
- No response-body or secret-bearing HTTP error logging by this plugin; native host credential storage and other host logging remain outside its control.
- Concurrent-operation and overwrite protections, tested with synthetic credentials.

## Limits

ECPA owns saved credentials and its inference/access rules. This is not Windows vault encryption. The host save API has no cross-client compare-and-save transaction; coordinate edits made by other plugins or management clients. Provider policies, key billing classification, account scopes and live OAuth compatibility require separate live verification. Future upstream changes and binaries need their own review. We have not audited the Go compiler, OS, proxy core or every transitive build tool.

The private HTTP client honours standard proxy environment variables, but not ECPA per-account proxy configuration. A configured network proxy is part of the trust boundary. Provider responses remain untrusted data; these controls do not prevent a model or remote service from returning hostile content.

## Test-only code

`fixture_transport.go` is guarded by the `integration_fixture` Go build tag. It returns synthetic provider responses without contacting any provider. It is excluded from normal builds and must never be shipped. Release packaging clears inherited GOFLAGS and verifies build settings. Fixture DLLs use a separate output directory. Test account keys/codes are synthetic, never personal credentials.
