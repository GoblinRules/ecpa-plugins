# Independent plugin releases

## Structure

`ecpa-plugins` remains the source workspace and public registry. Each plugin owns its version and repository in `plugins/<id>/Cargo.toml`. Shared crate versions do not determine plugin versions.

Each registry entry points to a dedicated public `GoblinRules/ecpa-<plugin-id>` release repository. CLIProxyAPI resolves that repository's latest release, so updating MCP Manager no longer makes every other plugin appear outdated. Source stays together to avoid copying shared code. Releases record an immutable source commit and include a full source archive.

## Publish one plugin

1. Change only that plugin's version in its Cargo.toml. Use numeric major.minor.patch versions. New plugins can start at 0.1.0.
2. Run `cargo check --workspace --offline` to update the lockfile, then validation, formatting, Clippy and relevant tests. Shared-code changes may require releases of several affected plugins, but do not automatically bump others.
3. Commit and push the source revision.
4. In the plugin's release repository, run **Actions → Publish plugin release** with the full source commit SHA. Its own Actions token publishes the release; no cross-repository secret is required. Builds use `--locked`; existing releases cannot be replaced.
5. Verify anonymous downloads, hashes, runtime metadata and installation in an isolated core.

Local alternative with an authenticated GitHub CLI:

```powershell
python scripts/package.py --plugin mcp-manager
python scripts/publish.py --plugin mcp-manager --repository GoblinRules/ecpa-mcp-manager --notes-file release-notes.txt
```

Without `--plugin`, packaging builds all current versions. Each plugin's ZIP, checksums.txt and release.json live in `dist/<plugin-id>/`. Publishing adds a full source workspace ZIP and uploads an explicit artifact list, excluding stale versions.

Archives use `<plugin-id>_<version>_windows_amd64.zip`, containing exactly `<plugin-id>.dll`. DLL metadata uses the plugin's own package version, including plugins built with the shared suite macro. SHA-256 checksums cover the binary archive. release.json records its digest and source revision. Source archives include shared workspace dependencies.

The central repo's manual build workflow uploads CI artifacts only. Actual releases belong in the dedicated repositories. The canonical workflow template is under `distribution/templates/`; `scripts/prepare-release-repo.py` generates a new release repository's files.

## Migration from collection releases

Historical versions through 0.6.1 remain in the central repository unchanged. All seven plugins move to 0.6.2 once to update repository metadata and preserve normal upgrades. Subsequent versions advance independently. Matching numbers at migration do not imply a shared version.

Plugin IDs, the registry URL, configuration, data directories and backups stay unchanged. Refresh the existing store source, update, then restart the core if prompted. Do not reset published 0.6.1 plugins to 0.1.0: that would appear as a downgrade.

Stage migration on a branch. Publish and verify all dedicated repositories before fast-forwarding master and switching the stable registry to them.
