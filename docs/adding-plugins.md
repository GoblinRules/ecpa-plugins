# Adding a plugin

1. Create `plugins/<plugin-id>/` with `Cargo.toml`, `src/`, `tests/`, and a README. Add `web/`, `assets/`, or `scripts/` only when needed.
2. Match the Cargo package name to the registry ID. Use `version.workspace = true` and a library with `crate-type = ["cdylib", "rlib"]`. The `plugins/*` workspace discovers it automatically. Use the default library name (package ID with hyphens changed to underscores).
3. Implement the CLIProxyAPI native ABI and declare only capabilities the plugin uses. Keep private file/data endpoints behind authenticated management routes.
4. Add a `registry.json` entry with its ID, name, description, author and this repository URL. Include license and useful tags. Do not add placeholder entries for unimplemented plugins.
5. Document purpose, supported platforms, requirements, configuration, authentication, data locations, limitations, test commands and upgrade behaviour in the plugin README. Add it to the root catalogue.
6. Add tests with isolated fixture data. Do not use personal agent files, credentials, or installed production cores as test fixtures.
7. Run root validation, Rust checks, and packaging. The shared release tool packages every registry entry and generates one checksums file.

All current plugins are Rust native libraries distributed for Windows x64. A plugin written in another language needs an explicit shared build adapter and CI support before it can be added. Do not list unsupported platforms as downloadable.

The registry supports entries pointing to other repositories, but this collection's validator deliberately requires local entries to point here. Independently versioned plugins should use a separate release repository and a corresponding update to the validator/tooling.
