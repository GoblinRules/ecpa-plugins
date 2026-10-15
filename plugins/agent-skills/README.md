# Agent Skills

View, create and edit local SKILL.md files with validation and backups.

## Install and open

Add the [collection registry](../../README.md#add-the-registry), then install **Agent Skills** from ECPA's Plugin store. Open its page from the plugin card and unlock it with the proxy management key. Windows x64, tested with CLIProxyAPI v8.0.29 / RPC schema 6.

## Manage local skills

1. Select an existing skill to inspect or edit its SKILL.md.
2. For a new skill, choose **New**, select a root, enter a folder name, and write YAML frontmatter with name and description followed by instructions.
3. **Preview changes** shows the destination and content; **Apply reviewed changes** saves it.
4. Use **Previous versions** to preview restoration of an older SKILL.md.

## Scope and limitations

Scans one folder level under configured roots, up to 500 entries. Defaults: Claude Code ~/.claude/skills and Codex ~/.agents/skills. An optional extra root can target a project or legacy ~/.codex/skills. Hidden folders, including system/package caches, are not scanned. Linked files/directories are refused. Existing scripts, references, and assets remain untouched. It does not install remote skills, copy bundles, run scripts, delete skill folders, or guarantee agent discovery. Frontmatter validation checks YAML syntax and non-empty name/description, not the entire skills specification.

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

The isolated core test covers this plugin's real DLL and authenticated routes. Add `--serve`, open this plugin's `/v0/resource/plugins/agent-skills/editor` page, and evaluate `tests/suite-browser-check.js` for its UI workflow. Do not run fixture tests against personal files. This plugin has its own version and release repository; the shared registry URL stays unchanged.

## Releases

Binaries and per-plugin releases: [ecpa-agent-skills](https://github.com/GoblinRules/ecpa-agent-skills). Source and shared code remain in this workspace. See [independent releases](../../docs/releases.md).
