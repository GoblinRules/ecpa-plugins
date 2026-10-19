# ECPA Plugins

A collection of native plugins for **EasyCLIProxyAPI / CLIProxyAPI**, with a public registry for installation and updates.

## Add the registry

Paste this URL into **Advanced settings → Extensions & integrations → Additional plugin registries**, then save:

```text
https://raw.githubusercontent.com/GoblinRules/ecpa-plugins/master/registry.json
```

Open **Plugins → Plugin store**, refresh, and choose a plugin. Complete ECPA's source confirmation and restart the core if prompted. No registry authentication is needed. Individual plugins may require the proxy management key.

## Available plugins

- **[Connections Manager](plugins/connections-manager/README.md)** — Named Cloudflare/GitHub accounts in Windows Credential Manager, project assignments and a CLI/MCP launcher shared across agents.

- **[Agent Instructions](plugins/agent-instructions/README.md)** — edit global instructions for Claude Code, Codex, Kimi Code, Grok Build, ZCode, and Antigravity. Includes backups, restore, conflict detection, and optional remembered login. Windows x64; tested with CLIProxyAPI v8.0.29.

- **[Agent Profiles](plugins/agent-profiles/README.md)** — Named instruction sets with previewed application and backups.
- **[MCP Manager](plugins/mcp-manager/README.md)** — Add, edit, duplicate and remove individual servers; assign supported definitions to Claude Code and Codex with previews and backups.
- **[Agent Diagnostics](plugins/agent-diagnostics/README.md)** — Read-only checks of instruction paths, file health and configuration syntax.
- **[Prompt Library](plugins/prompt-library/README.md)** — Searchable local prompts and instruction snippets with tags.
- **[Config Snapshots](plugins/config-snapshots/README.md)** — Capture and selectively restore supported agent files with change previews.
- **[Agent Skills](plugins/agent-skills/README.md)** — View, create and edit local SKILL.md files with validation and backups.

## Interface and artwork

All plugins include distinct vector artwork. Agent-specific controls reuse the same product icons as Agent Instructions. Editors follow ECPA’s Local Clients layout: charcoal panels, blue accents, persistent left navigation and a spacious editor. Embedded pages retain the sidebar above 650px; phone-sized Instructions views use an agent selector.

Plugin/store metadata publishes HTTPS logo URLs. Current ECPA versions that hardcode puzzle icons need the upstream card-logo UI change to display them; plugin updates cannot change host app buttons or cards. Find in store / Check for updates is also an ECPA app change (PR #458).

## Independent versions

Source and shared libraries stay here. Each plugin has its own public release repository:

- [agent-instructions](https://github.com/GoblinRules/ecpa-agent-instructions/releases)
- [agent-profiles](https://github.com/GoblinRules/ecpa-agent-profiles/releases)
- [mcp-manager](https://github.com/GoblinRules/ecpa-mcp-manager/releases)
- [agent-diagnostics](https://github.com/GoblinRules/ecpa-agent-diagnostics/releases)
- [prompt-library](https://github.com/GoblinRules/ecpa-prompt-library/releases)
- [config-snapshots](https://github.com/GoblinRules/ecpa-config-snapshots/releases)
- [agent-skills](https://github.com/GoblinRules/ecpa-agent-skills/releases)

The migration uses 0.6.2 once for all seven to preserve upgrades from 0.6.1. Future releases advance independently. Your registry URL and saved configuration stay the same.

## Repository layout

```text
registry.json                     Public store catalogue (stable URL)
Cargo.toml / Cargo.lock            Shared Rust workspace and locked dependencies
plugins/
  agent-instructions/
    README.md                     Installation, usage, limitations, API
    Cargo.toml                    Independent version and release repository
    src/                          Native plugin and file storage
    web/                          Embedded editor
    tests/                        Core integration and browser checks
    scripts/                      Plugin-specific build entry point
crates/agent-files/               Shared file protections and instruction paths
crates/plugin-suite/              Shared native bridge, workflows and UI
tests/                            Isolated suite integration/browser checks
scripts/                          Shared validation and release packaging
distribution/                     Release-repository templates
docs/                             Development and release guidance
.github/workflows/                CI and publication
assets/                           Repository artwork
dist/                             Generated release ZIPs (not committed)
```

## Development

See the [2026-10-17 compatibility review](docs/compatibility.md) for the updated
plugin contract, lifecycle handling and real-core verification on CLIProxyAPI v8.0.32.

Requires Rust stable, a native linker, and Python 3.11+.

```powershell
python scripts/validate.py
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
python scripts/package.py
```

See [adding a plugin](docs/adding-plugins.md) and [release process](docs/releases.md). Each plugin owns its implementation, documentation and tests. Each plugin has its own release repository and version. Build one with `python scripts/package.py --plugin <id>`. See [release repository structure](distribution/README.md).

MIT license; see [LICENSE](LICENSE).
