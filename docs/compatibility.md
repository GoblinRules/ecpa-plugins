# Plugin contract review — 2026-10-17

Reviewed the current [development guide](https://help.router-for.me/cn/plugin/development)
and [Management API guide](https://help.router-for.me/cn/plugin/management-api.html)
against all seven plugins. Verified on Windows x64 using the official CLIProxyAPI
v8.0.32 release, with its ZIP checked against the published SHA-256 checksum.

## Contract decisions

| Area | Result |
| --- | --- |
| Native ABI | Keep ABI version 1, C-compatible function tables, JSON envelopes and plugin-owned buffer freeing. |
| RPC schema | Keep schema version 6. The guide's version 1 is an example; the current SDK defines version 6 for preserving raw management JSON. This matters for exact Markdown and configuration round trips. |
| Resource pages | Keep `/v0/resource/plugins/<id>/editor`. Public GET requests return bundled UI only; they do not read agent files or execute writes. |
| File APIs | Keep authenticated `/v0/management/<id>/...` routes. These work on v8.0.32; the core's v8 management APIs do not imply migrating plugin routes to `/v8`. |
| Browser login | Keep manual unlock and optional remembered keys. Same-origin reuse of a management centre's stored key is permitted, not required. The guide specifies no stable storage key or authentication bridge to depend on. |
| Scripts | Already bundled into the plugin; no external JavaScript is loaded into the privileged origin. |
| Configuration | Keep validation on register/reconfigure and existing custom file-location fields. Invalid configuration does not replace the active configuration. |
| Packaging | Registry schema 1, independent release repositories, root-level DLL, platform ZIP naming and SHA-256 checksums already match. |
| Host callbacks | Not needed for these local-file workflows. If future features call host model execution, propagate `host_callback_id` and close streaming handles as documented. |

Schema and lifecycle behavior were checked against
[SDK revision 911f49c](https://github.com/router-for-me/CLIProxyAPI/blob/911f49cbd49f4fe2516979754a7488a3fd14fe64/sdk/pluginabi/types.go)
and the corresponding `internal/pluginhost/host.go`.

## Lifecycle improvement

The existing plugins were loadable on v8.0.32. The host tolerates their previously
unsupported `plugin.quiesce` message, so this is an unload improvement rather than
a fix for a broken ABI.

Both native implementations now acknowledge quiesce and shutdown. Operations are
synchronous under their existing mutexes; no background workers or host streams
need draining. The suite discards pending write previews on quiesce and shutdown,
and shutdown clears in-memory configuration. The native shutdown callback uses the
same cleanup path. Repeated shutdown is harmless; registration can initialize a
fresh instance afterward. Cleanup does not alter user files or saved configuration.

## Verification

- 20 Rust tests, strict workspace Clippy, formatting and registry validation.
- Three release-tool tests covering artifact selection and source packaging.
- Both isolated real-core integration suites on v8.0.32: all seven DLLs, authenticated
  data access, public resource boundaries, file preservation, conflicts, backups,
  custom paths and the MCP/profile/skill/snapshot/prompt workflows.
- Targeted unload through `DELETE /v0/management/plugins/<id>` for both native
  implementations, checking DLL removal and continued core operation. The suite
  additionally verifies another plugin remains usable.

These changes are source-only until the next patch releases. Published ZIPs and
registry version hints are unchanged; do not replace an existing release asset.
Release affected plugins independently (MCP Manager 0.7.1; the other six 0.6.4)
using the normal [release process](releases.md).
