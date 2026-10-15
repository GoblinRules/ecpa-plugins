# Releases

## Version policy

CLIProxyAPI resolves the **latest GitHub release of each entry's repository** and uses its dotted numeric tag as the plugin version. Plugins in this repository therefore share one collection version in `[workspace.package]` of the root `Cargo.toml`.

Every release must contain **all registered plugins**, even when only one changed. Per-plugin tags or a latest release containing only one plugin would break installation of the others. For independent version schedules, use separate release repositories instead.

## Publish

1. Change the shared version, run `cargo check --workspace` to update `Cargo.lock`, and describe changes in the relevant plugin README as needed.
2. Run `python scripts/validate.py`, Rust formatting/lint/tests, plugin integration checks, and `python scripts/package.py`.
3. Commit and push, then push a matching new tag, for example `v0.3.1`.
4. The release workflow checks the tag, builds every registered Windows x64 plugin, and publishes the ZIPs plus one `checksums.txt`. Existing releases are left untouched.
5. Verify anonymous registry/release downloads and try installation through an isolated core before announcing the update.

Archives use `<plugin-id>_<version>_windows_amd64.zip` and contain exactly `<plugin-id>.dll` at the root. Checksums use SHA-256. Packaging removes nothing from `dist`; it replaces the current-version archives and writes checksums only for the plugins built in that invocation. CI starts clean and publishes only the current build.

The public registry URL remains at `/master/registry.json`. Do not move it when reorganising plugin source code. The existing v0.3.0 release remains installable after the source-folder reorganisation; no replacement DLL is needed for that change alone.
