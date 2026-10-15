# Agent Instructions

A native instruction-file editor for EasyCLIProxyAPI / CLIProxyAPI. The editor supports Claude Code, Codex, Kimi Code, Grok Build, Z.ai/ZCode, and Antigravity.

## Install from the plugin store

Add this URL to **Advanced settings → Extensions & integrations → Additional plugin registries**, then save settings:

```text
https://raw.githubusercontent.com/GoblinRules/ecpa-plugins/master/registry.json
```

Open **Plugins → Plugin store**, refresh, and search for **Agent Instructions**. Review the source and complete ECPA's third-party installation confirmation, then install (or update an existing copy). Restart the core if prompted.

Open the editor with the **Agent Instructions** button on its plugin card. This plugin does not add an ECPA sidebar entry. The registry is public and requires no registry authentication. It is separate from the official plugin store.

Updates come from this repository's latest GitHub release; the registry URL stays the same. Currently distributed and tested on **Windows x64**, using **CLIProxyAPI v8.0.29**. Requires a plugin-enabled core supporting RPC schema 6; older schemas can alter HTML-like text.

## Editor features

- Global instruction editing with exact file paths and missing-file creation.
- Backups, checksum-verified restore, and conflict detection for external edits.
- Atomic replacement, UTF-8 support up to 1 MiB, and existing CRLF preservation.
- Codex override guidance and agent-specific notes.
- Authenticated file endpoints and optional remembered login.

### Remember key on this device

Enter your proxy **management key**, not a client API key. Check **Remember key on this device** before unlocking to save a successfully validated key in browser localStorage and automatically unlock next time. Otherwise it stays in page memory only.

Storage belongs to that browser profile and proxy origin (scheme, hostname and port). ECPA's embedded browser and an external browser have separate storage. The plugin does not encrypt localStorage; other scripts on the same proxy origin can access it. **Lock & forget** removes the saved key. Authentication rejection also clears it; storage failures fall back to session-only use with an explanation.

## Supported files

Paths below are relative to the **proxy user's home**, on the machine running the core:

- Claude Code: `.claude/CLAUDE.md` (`CLAUDE_CONFIG_DIR` overrides the directory).
- Codex: `.codex/AGENTS.md` and `.codex/AGENTS.override.md` (`CODEX_HOME` overrides the directory).
- Kimi Code: `.kimi-code/AGENTS.md` (`KIMI_CODE_HOME` overrides the directory); targets current Kimi Code CLI, not older versions lacking global instructions.
- Grok Build: `.grok/AGENTS.md`; targets the official xAI client, not third-party tools using `GROK.md`.
- Z.ai / ZCode: `.zcode/AGENTS.md`. Z.ai models used through Claude Code still use Claude Code's file.
- Antigravity: `.gemini/GEMINI.md` and `.gemini/AGENTS.md`. Rules accumulate across scopes; GEMINI.md may also affect Gemini CLI.

Environment overrides must be absolute paths and present in the **core process** environment. The plugin-specific `AGENT_INSTRUCTIONS_HOME` overrides its base home for portable profiles and tests; agent-specific overrides take precedence. It does not change which files the agents themselves load.

### Custom file locations

Open **Plugins > Agent Instructions > Configure**. Set an optional field to an **absolute file path including its filename**, save configuration, and reload the editor. Leave a field blank to restore its default/environment-based location.

| Configuration field | Instruction file |
| --- | --- |
| `claude_path` | Claude Code CLAUDE.md |
| `codex_path` | Codex AGENTS.md |
| `codex_override_path` | Codex AGENTS.override.md |
| `kimi_path` | Kimi Code AGENTS.md |
| `grok_path` | Grok Build AGENTS.md |
| `zcode_path` | Z.ai / ZCode AGENTS.md |
| `antigravity_path` | Antigravity GEMINI.md |
| `antigravity_agents_path` | Antigravity AGENTS.md |

For example, enter `D:\Agent Rules\CLAUDE.md` directly in Configure. Paths refer to the **machine running the core**, not the browser device. Relative paths, `~`, and environment-variable expressions are not expanded. Missing parent directories are created on first save. Existing directories are rejected as file targets.

Overrides take precedence over environment-based defaults. They only choose which files this editor opens: configure the agent separately to load those files. Existing files and backups are **not moved**. Backups stay beside their target; switching back to a previous location makes its backups available again. An editor opened before a location change receives a conflict when saving to the new target, even with identical contents. Copy any draft before reloading.

For YAML configuration, add these fields under `plugins.configs.agent-instructions`, for example `claude_path: 'D:\Agent Rules\CLAUDE.md'` (single quotes preserve Windows backslashes).

A non-empty Codex override replaces its global AGENTS.md. Clear the override to fall back. Start a new agent session after saving. The default locations cover global files; use an explicit override for an alternate location. No files are created until Save.

Backups live in `.agent-instructions-backups/<file-id>/<sha256>.md` under the corresponding file's parent. Identical previous versions are deduplicated; backups are not automatically pruned. Restore backs up the current content before replacing it. First creation has no previous content to back up.

Only the eight configured file slots are allowed; file API requests cannot supply arbitrary paths. Linked files/directories (including Windows junctions), invalid UTF-8, and oversized files are rejected. Atomic writes preserve ordinary permissions but do not explicitly copy custom Windows ACLs or alternate streams. Content is checked before saving and again before replacement; a narrow race with unrelated external editors remains.

## Manual installation / upgrading

Stop the core, extract `agent-instructions.dll` from the Windows release ZIP into the core's configured `plugins` directory, and restart. A relative plugin directory resolves from the core installation directory (normally `cpa-core` beside the ECPA executable). The folder icon in the Plugins page is a label, not a button.

Enable plugins globally and enable **Agent Instructions**. If configuring by YAML, merge without replacing unrelated settings:

```yaml
plugins:
  enabled: true
  dir: "plugins"
  configs:
    agent-instructions:
      enabled: true
```

The DLL must be directly in that folder or its `windows/amd64` subdirectory, without duplicate copies. Existing backups remain compatible across upgrades. The default editor URL is `http://127.0.0.1:8317/v0/resource/plugins/agent-instructions/editor`.

## Development and verification

Run the commands below from the repository root. Requires Rust stable and a native linker (Visual Studio C++ Build Tools on Windows), plus Python 3.11+.

```powershell
cargo fmt --check
cargo clippy --all-targets --locked -- -D warnings
cargo test --locked
python scripts/package.py
python plugins/agent-instructions/tests/integration.py --core C:/path/to/cli-proxy-api.exe
```

Integration tests launch a real core on a random loopback port with isolated temporary instruction files. They verify DLL loading, authentication, Markdown round trips, all supported file mappings, saves, backups, restores, and conflicts. Add `--serve` for browser verification; the fixture prints its URL and test key. Unlock the fixture and evaluate `plugins/agent-instructions/tests/browser-check.js` for the editing workflow, or start locked and evaluate `plugins/agent-instructions/tests/remember-check.js` for remembered-login checks. Reload/automatic login is additionally checked by browser navigation. Stop the test process when done.

The only public resource is static HTML. File operations use authenticated routes:

```text
GET  /v0/management/agent-instructions/files
GET  /v0/management/agent-instructions/backups?id=claude
PUT  /v0/management/agent-instructions/file
POST /v0/management/agent-instructions/restore
```

Save body: `{ "id": "claude", "version": "<last-read version>", "content": "..." }`.
Restore body: `{ "id": "claude", "version": "<last-read version>", "backup": "<hash>.md" }`.
Version tokens are opaque and bind the resolved path and content, including for missing files. Always use the token returned by `/files`. Conflicts return HTTP 409 and retain the editor draft. Authentication is enforced by the core. Native plugins share its process and origin trust boundary. The editor has no CDN dependencies or telemetry; instruction content is displayed as text.

## Repository and releases

Source: `plugins/agent-instructions/`. Shared build commands run from the repository root; this plugin inherits the collection version. See [release process](../../docs/releases.md) and [adding plugins](../../docs/adding-plugins.md). The registry URL remains unchanged.

## References

- [Official plugin ABI examples](https://github.com/router-for-me/CLIProxyAPI/tree/main/examples/plugin)
- [Store format](https://github.com/router-for-me/CLIProxyAPI-Plugins-Store)
- [Kimi instructions](https://moonshotai.github.io/kimi-code/en/customization/agents)
- [Grok Build instructions](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/01-getting-started.md)
- [ZCode configuration](https://zcode.z.ai/en/docs/qa)
- [Antigravity rules](https://antigravity.google/docs/rules/)

MIT license; see [LICENSE](../../LICENSE).


## v0.4.0 interface update

Agent navigation is grouped into six compact sections with embedded product icons. Codex and Antigravity expose related files within their own group, and narrow layouts use a two-column agent grid. Icons load offline and retain their attribution in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the embedded page source.
