# Agent Diagnostics

Read-only checks of instruction paths, file health and configuration syntax.

## Install and open

Add the [collection registry](../../README.md#add-the-registry), then install **Agent Diagnostics** from ECPA's Plugin store. Open its page from the plugin card and unlock it with the proxy management key. Windows x64, tested with CLIProxyAPI v8.0.29 / RPC schema 6.

## Run checks

Open the plugin and unlock it. **Reload** reruns checks for all supported instruction slots and the Claude/Codex configuration files. Rows report the resolved path, byte size, missing/unreadable files, JSON/TOML syntax, read-only permission hints, and non-empty Codex overrides.

## Scope and limitations

Strictly read-only: no write routes, process execution, or network probes. It does not establish effective ACL write permission, detect installed agent versions, or prove that an agent loaded a file. It checks configuration syntax rather than every vendor-specific schema rule. The authenticated response does not include file content.

## Configuration, storage, and safety

Use the plugin card's **Configure** button for custom absolute paths on the machine running the core. Blank values retain defaults. Settings change the editor's targets, not what an agent itself loads. Restart the affected agent session after applying changes.

See [shared configuration and safety details](../../docs/agent-tools.md) for exact fields, authentication, storage paths, backups, conflict behavior, partial-apply handling, and limits. The instruction path settings are independent for each plugin; copy any custom settings from Agent Instructions when needed.

## Verification and implementation

Shared implementation: `crates/plugin-suite`; native entry point: this folder's `src/lib.rs`. File protection is shared with Agent Instructions through `crates/agent-files`.

```powershell
cargo test --workspace --locked
python scripts/package.py
python tests/suite_integration.py --core C:/path/to/cli-proxy-api.exe
```

The isolated core test covers this plugin's real DLL and authenticated routes. Add `--serve`, open this plugin's `/v0/resource/plugins/agent-diagnostics/editor` page, and evaluate `tests/suite-browser-check.js` for its UI workflow. Do not run fixture tests against personal files. This plugin has its own version and release repository; the shared registry URL stays unchanged.

## Releases

Binaries and per-plugin releases: [ecpa-agent-diagnostics](https://github.com/GoblinRules/ecpa-agent-diagnostics). Source and shared code remain in this workspace. See [independent releases](../../docs/releases.md).
