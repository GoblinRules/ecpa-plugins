# MCP Manager

Manage individual Claude Code and Codex MCP servers with configuration forms, cross-agent assignment, previews and backups.

## Install and open

Add the [collection registry](../../README.md#add-the-registry), then install **MCP Manager** from ECPA's Plugin store. Open its page from the plugin card and unlock it with the proxy management key. Windows x64, tested with CLIProxyAPI v8.0.29 / RPC schema 6.

## Edit MCP servers

1. Choose Claude Code or Codex.
2. Select a server or choose **Add server**. Edit its name, transport, command/arguments or URL, and environment variables or headers. Values are masked in the form; Advanced JSON and full-file previews can show credentials.
3. Choose **Advanced JSON** to edit a single native server definition, including client-specific fields. Those fields survive ordinary form edits.
4. Select **Apply to agents** to write this server to Claude Code, Codex, or both. Unchecked agents remain unchanged. These are explicit copies, not ongoing automatic synchronization.
5. Choose **Preview changes**, review every destination file, then apply. Different same-name servers require the explicit replacement checkbox. Unrelated servers and configuration settings are retained.
6. **Duplicate** creates a new draft. Renaming removes the old name only from the source agent when it is selected. **Remove from this agent** previews deletion from that agent alone; copies in other agents remain.
7. Select a previous version under **Previous versions** to preview a full-file restore.

### Supported cross-agent translation

- Local stdio: command, string arguments and string environment variables.
- Streamable HTTP: URL and literal string headers (`headers` in Claude, `http_headers` in Codex). Claude receives `type: http`; Codex does not receive Claude's `type` field.
- Claude SSE/WebSocket can be edited in place, but cannot be copied to Codex through this manager.
- Client-specific fields without a supported equivalent, such as Codex token environment references or tool restrictions, block cross-agent copying with an explanation. They remain available when editing that agent alone.

Existing files are read on opening; there is no migration or separate server catalogue. Assignment updates agent configuration files and requires those agents to reload/restart. It does not start or test servers.

## Scope and limitations

Supports Claude Code user-level mcpServers in ~/.claude.json and Codex mcp_servers in CODEX_HOME/config.toml. Unrelated JSON values and TOML settings are preserved; JSON formatting and the replaced TOML MCP section may be reformatted. Server commands are never executed here. Registry discovery, connectivity testing, OAuth login, process supervision, managed gateways and project discovery are not included in this release. Configure explicit paths to target a project file with the corresponding format.

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

The isolated core test covers this plugin's real DLL and authenticated routes. Add `--serve`, open this plugin's `/v0/resource/plugins/mcp-manager/editor` page, and evaluate `tests/mcp-browser-check.js` for add/assign/duplicate/rename/delete/translation/restore-preview workflows. `tests/reference-layout.cjs` also checks its embedded layout. Do not run fixture tests against personal files. This plugin has its own version and release repository; the shared registry URL stays unchanged.

## Releases

Binaries and per-plugin releases: [ecpa-mcp-manager](https://github.com/GoblinRules/ecpa-mcp-manager). Source and shared code remain in this workspace. See [independent releases](../../docs/releases.md).
