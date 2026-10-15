# Config Snapshots

Capture and selectively restore supported agent files with change previews.

## Install and open

Add the [collection registry](../../README.md#add-the-registry), then install **Config Snapshots** from ECPA's Plugin store. Open its page from the plugin card and unlock it with the proxy management key. Windows x64, tested with CLIProxyAPI v8.0.29 / RPC schema 6.

## Capture and restore

1. Choose **New**, give the snapshot an ID and name, then select existing files.
2. **Capture selected current files** copies their content into a draft; **Save record** persists it.
3. Choose a snapshot and select the saved files you want to restore.
4. **Preview changes** shows each current destination and complete before/after content. Apply only after review.

## Scope and limitations

Includes the eight instruction slots plus Claude Code user JSON and Codex TOML. This is a selected-file snapshot, not a complete agent/account backup. Credential databases, OAuth state, installed packages, and skill supporting files are excluded. Snapshots retain contents, not original paths, absence/deletion state, timestamps, or ACLs. Restore writes the current configured slots. Configuration snapshots can contain secrets; storage and backups are not encrypted.

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

The isolated core test covers this plugin's real DLL and authenticated routes. Add `--serve`, open this plugin's `/v0/resource/plugins/config-snapshots/editor` page, and evaluate `tests/suite-browser-check.js` for its UI workflow. Do not run fixture tests against personal files. Releases share the collection version and are installed through the same registry URL.
