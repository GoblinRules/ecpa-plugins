# Release repositories

The central workspace owns source, shared crates, artwork, tests and the stable registry URL. Each `registry.json` entry points to a separate public `GoblinRules/ecpa-<plugin-id>` repository containing release documentation and a publishing workflow.

This separates release discovery without duplicating shared Rust or UI source. The plugin's own `plugins/<id>/Cargo.toml` supplies its version and release repository. Shared crate versions do not control plugin versions.

`templates/release.yml` is the canonical workflow template. `python scripts/prepare-release-repo.py --plugin <id> --output <empty-directory>` creates a new release repository's files. Existing generated repositories are not rewritten automatically; workflow changes must be applied to them deliberately.

Historical collection releases remain in the central repository. The public registry URL and all plugin IDs stay unchanged. See [release instructions](../docs/releases.md) for migration and publication.
