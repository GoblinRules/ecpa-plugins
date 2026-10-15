# Agent Profiles

Named instruction sets with previewed application and backups.

## Install and open

Add the [collection registry](../../README.md#add-the-registry), then install **Agent Profiles** from ECPA's Plugin store. Open its page from the plugin card and unlock it with the proxy management key. Windows x64, tested with CLIProxyAPI v8.0.29 / RPC schema 6.

## Use a profile

1. Choose **New**, give the profile a unique ID, name, and optional tags.
2. Select existing instruction files and click **Capture selected current files**.
3. Edit each saved file using the file selector, then **Save record**.
4. Select the saved files to apply, choose **Preview changes**, inspect destinations and current/proposed contents, then **Apply reviewed changes**.

## Scope and limitations

Supports the same eight instruction slots as Agent Instructions. Files are captured independently; missing files are not silently captured as empty. Applying a stored file can create a missing target. A profile targets the currently configured slots, not the original capture paths. There is no background synchronization or active-profile enforcement.

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

The isolated core test covers this plugin's real DLL and authenticated routes. Add `--serve`, open this plugin's `/v0/resource/plugins/agent-profiles/editor` page, and evaluate `tests/suite-browser-check.js` for its UI workflow. Do not run fixture tests against personal files. This plugin has its own version and release repository; the shared registry URL stays unchanged.

## Releases

Binaries and per-plugin releases: [ecpa-agent-profiles](https://github.com/GoblinRules/ecpa-agent-profiles). Source and shared code remain in this workspace. See [independent releases](../../docs/releases.md).
