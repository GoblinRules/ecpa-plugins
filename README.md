# ECPA Plugins

A collection of native plugins for **EasyCLIProxyAPI / CLIProxyAPI**, with a public registry for installation and updates.

## Add the registry

Paste this URL into **Advanced settings → Extensions & integrations → Additional plugin registries**, then save:

```text
https://raw.githubusercontent.com/GoblinRules/ecpa-plugins/master/registry.json
```

Open **Plugins → Plugin store**, refresh, and choose a plugin. Complete ECPA's source confirmation and restart the core if prompted. No registry authentication is needed. Individual plugins may require the proxy management key.

## Available plugins

- **[Agent Instructions](plugins/agent-instructions/README.md)** — edit global instructions for Claude Code, Codex, Kimi Code, Grok Build, ZCode, and Antigravity. Includes backups, restore, conflict detection, and optional remembered login. Windows x64; tested with CLIProxyAPI v8.0.29.

## Repository layout

```text
registry.json                     Public store catalogue (stable URL)
Cargo.toml / Cargo.lock            Shared Rust workspace and version
plugins/
  agent-instructions/
    README.md                     Installation, usage, limitations, API
    Cargo.toml                    Plugin package
    src/                          Native plugin and file storage
    web/                          Embedded editor
    tests/                        Core integration and browser checks
    scripts/                      Plugin-specific build entry point
scripts/                          Shared validation and release packaging
docs/                             Development and release guidance
.github/workflows/                CI and publication
assets/                           Repository artwork
dist/                             Generated release ZIPs (not committed)
```

## Development

Requires Rust stable, a native linker, and Python 3.11+.

```powershell
python scripts/validate.py
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
python scripts/package.py
```

See [adding a plugin](docs/adding-plugins.md) and [release process](docs/releases.md). Each plugin owns its implementation, documentation and tests. Shared tooling builds all registered plugins together because the store resolves this repository's latest release.

MIT license; see [LICENSE](LICENSE).
