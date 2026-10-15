# MCP Manager

Edit Claude Code and Codex MCP server definitions with previews and backups.

## Install and open

Add the [collection registry](../../README.md#add-the-registry), then install **MCP Manager** from ECPA's Plugin store. Open its page from the plugin card and unlock it with the proxy management key. Windows x64, tested with CLIProxyAPI v8.0.29 / RPC schema 6.

## Edit MCP servers

1. Choose Claude Code or Codex.
2. Edit the JSON object mapping server names to settings. Use an empty object to remove all user-level server definitions.
3. Choose **Preview changes** and review the complete resulting config before applying.
4. Select a previous version under **Previous versions** to preview a full-file restore.

## Scope and limitations

Supports Claude Code user-level mcpServers in ~/.claude.json and Codex mcp_servers in CODEX_HOME/config.toml. Unrelated JSON values and TOML settings are preserved; JSON formatting and the replaced TOML MCP section may be reformatted. Server commands are never executed here. No connectivity testing, OAuth login, automatic config translation, plugin-provided server management, or project discovery. Configure explicit paths to target a project file with the corresponding format.

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

The isolated core test covers this plugin's real DLL and authenticated routes. Add `--serve`, open this plugin's `/v0/resource/plugins/mcp-manager/editor` page, and evaluate `tests/suite-browser-check.js` for its UI workflow. Do not run fixture tests against personal files. This plugin has its own version and release repository; the shared registry URL stays unchanged.

## Releases

Binaries and per-plugin releases: [ecpa-mcp-manager](https://github.com/GoblinRules/ecpa-mcp-manager). Source and shared code remain in this workspace. See [independent releases](../../docs/releases.md).
