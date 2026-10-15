# Prompt Library

Searchable local prompts and instruction snippets with tags.

## Install and open

Add the [collection registry](../../README.md#add-the-registry), then install **Prompt Library** from ECPA's Plugin store. Open its page from the plugin card and unlock it with the proxy management key. Windows x64, tested with CLIProxyAPI v8.0.29 / RPC schema 6.

## Manage prompts

1. Choose **New** and enter a unique record ID, name, tags, and prompt text.
2. **Save record** stores it locally. Search matches names, IDs, and tags.
3. Select a prompt and **Copy content** to use it in an agent.
4. **Delete record** removes only the saved snippet; prior library contents are backed up.

## Scope and limitations

Prompts are not executed or inserted into conversations automatically. Plain text/Markdown is displayed literally. Clipboard access requires a browser/webview with clipboard permission. No remote sync or template-variable execution.

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

The isolated core test covers this plugin's real DLL and authenticated routes. Add `--serve`, open this plugin's `/v0/resource/plugins/prompt-library/editor` page, and evaluate `tests/suite-browser-check.js` for its UI workflow. Do not run fixture tests against personal files. This plugin has its own version and release repository; the shared registry URL stays unchanged.

## Releases

Binaries and per-plugin releases: [ecpa-prompt-library](https://github.com/GoblinRules/ecpa-prompt-library). Source and shared code remain in this workspace. See [independent releases](../../docs/releases.md).
