# Adding a plugin

1. Create `plugins/<plugin-id>/` with Cargo.toml, src, tests and README. Keep shared code/artwork in crates and assets.
2. Match the package name to the registry ID. Set explicit `version = "0.1.0"` and `repository = "https://github.com/GoblinRules/ecpa-<plugin-id>"`. Use cdylib and rlib crate types with the default library name. The plugins/* workspace discovers it automatically.
3. Implement the native ABI and only required capabilities. Authenticate private data endpoints. The suite macro passes the calling plugin's version and repository into shared runtime code.
4. Add a registry entry with matching release repository, ID, name, description, author, license, tags and artwork. Each plugin needs a distinct release repository.
5. Generate its README, license, identity and workflow with `python scripts/prepare-release-repo.py --plugin <id> --output <empty-directory>`. Create a public repository and push those files. Keep implementation source here.
6. Document usage, platforms, configuration, authentication, data paths, limits, tests and upgrades in the plugin README. Link it from the root catalogue.
7. Add isolated fixture tests. Run validation, Rust checks and relevant integration/browser tests. Build only this plugin with `python scripts/package.py --plugin <id>`.
8. Publish and verify its first release before publishing the registry change on master. See [releases](releases.md).

Current binaries target Windows x64. Non-Rust plugins need a build adapter and CI support. Shared crates are not installable plugins and do not get registry entries or release repositories.
