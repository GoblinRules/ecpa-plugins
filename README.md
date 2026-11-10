# ECPA Plugins

A collection of native plugins for **EasyCLIProxyAPI / CLIProxyAPI**, with a public registry for installation and updates.

## Add the registry

Paste this URL into **Advanced settings → Extensions & integrations → Additional plugin registries**, then save:

```text
https://raw.githubusercontent.com/GoblinRules/ecpa-plugins/master/registry.json
```

Open **Plugins → Plugin store**, refresh, and choose a plugin. Complete ECPA's source confirmation and restart the core if prompted. No registry authentication is needed. Individual plugins may require the proxy management key.

## Available plugins

- **[Claude Remote Login](plugins/claude-remote-login/README.md)** — Review and confirm a Claude account before adding it to ECPA, with protected reauthorisation.
- **[Z.ai Provider](plugins/zai-provider/README.md)** — Existing Coding Plan keys and explicitly configured optional browser login; no automatic key creation or client impersonation. Live provider/billing compatibility remains unverified.

- **[Connections Manager](plugins/connections-manager/README.md)** — Named Cloudflare/GitHub accounts in Windows Credential Manager, project assignments and a CLI/MCP launcher shared across agents.

- **[Agent Instructions](plugins/agent-instructions/README.md)** — edit global instructions for Claude Code, Codex, Kimi Code, Grok Build, ZCode, and Antigravity. Includes backups, restore, conflict detection, and optional remembered login. Windows x64; tested with CLIProxyAPI v8.0.29.

- **[Agent Profiles](plugins/agent-profiles/README.md)** — Named instruction sets with previewed application and backups.
- **[MCP Manager](plugins/mcp-manager/README.md)** — Add, edit, duplicate and remove individual servers; assign supported definitions to Claude Code and Codex with previews and backups.
- **[Agent Diagnostics](plugins/agent-diagnostics/README.md)** — Read-only checks of instruction paths, file health and configuration syntax.
- **[Prompt Library](plugins/prompt-library/README.md)** — Searchable local prompts and instruction snippets with tags.
- **[Config Snapshots](plugins/config-snapshots/README.md)** — Capture and selectively restore supported agent files with change previews.
- **[Agent Skills](plugins/agent-skills/README.md)** — View, create and edit local SKILL.md files with validation and backups.

## Shared services and machine management

- **[SSH & Machines](plugins/ssh-machines/README.md)** — Named machines, explicit SSH key/agent selection, independently verified host keys, connection checks and terminal commands.
- **[Managed MCP gateway](runtime/mcp-gateway/README.md)** — Connections Manager's separately installed worker for Bitwarden-backed service profiles and authenticated client access.
- **[Windows host readiness](runtime/mcp-gateway/HOST-READINESS.md)** — Required versus optional software, runtime identity/bootstrap, startup checks and hardware migration.
- **[Publication privacy audit](docs/publication-security-audit.md)** — Checked scope, historical compiler-path findings and release safeguards.

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
- [connections-manager](https://github.com/GoblinRules/ecpa-connections-manager/releases)
- [claude-remote-login](https://github.com/GoblinRules/ecpa-claude-remote-login/releases)
- [zai-provider](https://github.com/GoblinRules/ecpa-zai-provider/releases)
- [ssh-machines](https://github.com/GoblinRules/ecpa-ssh-machines/releases)

The original seven collection plugins used 0.6.2 once to preserve upgrades from 0.6.1. Releases now advance independently; newer plugins have their own version history. Your registry URL and saved configuration stay the same.

## Repository layout

The [managed MCP runtime](runtime/mcp-gateway/README.md) adds the
Connections Manager gateway, Bitwarden references and shared account profiles.
It is a separate native-Windows Python worker, delivered as an additional bundle
in Connections Manager releases; installing the DLL alone does not install Python. See the [host-readiness runbook](runtime/mcp-gateway/HOST-READINESS.md)
for required programs, bootstrap identity, startup checks and later host migration.

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
runtime/mcp-gateway/              SDK worker, profile templates, Windows setup and tests
tests/                            Isolated suite integration/browser checks
scripts/                          Shared validation and release packaging
distribution/                     Release-repository templates
docs/                             Development and release guidance
.github/workflows/                CI and publication
assets/                           Repository artwork
dist/                             Generated release ZIPs (not committed)
```

## Development

The two provider adaptations have a [security review and remaining limits](docs/provider-security-review.md).

See the [2026-10-17 compatibility review](docs/compatibility.md) for the updated
plugin contract, lifecycle handling and real-core verification on CLIProxyAPI v8.0.32.

Requires Rust stable, a native linker, and Python 3.11+. The two Go plugins also require the pinned [Go/Zig toolchain](docs/go-plugins.md); run `python scripts/setup_go.py` then `python scripts/check_go.py` before packaging them.

```powershell
python scripts/validate.py
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
python scripts/package.py
```

See [adding a plugin](docs/adding-plugins.md) and [release process](docs/releases.md). Each plugin owns its implementation, documentation and tests. Each plugin has its own release repository and version. Build one with `python scripts/package.py --plugin <id>`. See [release repository structure](distribution/README.md).

MIT license; see [LICENSE](LICENSE).
