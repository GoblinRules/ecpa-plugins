# Agent tools: configuration and safety

The six tools added in v0.6.0 are separate installable plugins. They share file
handling and a UI implementation, but each keeps independent configuration and
data. Agent Instructions remains independently installable.

## Paths

All paths refer to the core's machine and user. Use absolute paths; `~` and
environment-variable strings are not expanded. Blank settings use defaults.
Changing a setting does not move files, migrate backups, or configure an agent.

- Profiles, Diagnostics and Snapshots expose the same eight instruction path
  overrides as [Agent Instructions](../plugins/agent-instructions/README.md#custom-file-locations).
- MCP Manager, Diagnostics and Snapshots expose `claude_config_path`
  (default `~/.claude.json`) and `codex_config_path`
  (default `CODEX_HOME/config.toml`, normally `~/.codex/config.toml`).
- Profiles, Prompt Library and Snapshots expose `data_dir`. Their records live at
  `~/.ecpa-plugins/<plugin-id>/records.json` by default.
- Agent Skills exposes `claude_skills_dir` (default `CLAUDE_CONFIG_DIR/skills`,
  normally `~/.claude/skills`), `codex_skills_dir` (default `~/.agents/skills`),
  and optional `extra_skills_dir`. Use the extra root for project skills or legacy
  locations such as `~/.codex/skills`.
- `AGENT_INSTRUCTIONS_HOME` changes the base home for portable installations and
  isolated tests; `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `KIMI_CODE_HOME` retain
  their existing instruction-directory behavior.

## Authentication and storage

Only the static HTML page is public. Data and actions live under authenticated
`/v0/management/<plugin-id>/...` endpoints. Management credentials are never
included in page URLs. Instruction text is displayed as text, not executable HTML.

The **Remember key on this device** checkbox opts into localStorage at the proxy
origin, shared by these six tools (`ecpa-suite.management-key.v1`). The key is not
encrypted and other scripts on that origin can access it. Unchecked login keeps
the key in page memory. **Lock & forget** clears the current session and saved key;
other already-open tabs remain logged in until separately locked. Authentication
rejection clears the saved key. Browser profiles have separate storage.

Records and backups are local plaintext files. Configurations can include secrets;
restrict access to their directories using operating-system permissions. The tools
do not upload these files or invoke agent/MCP commands.

## Previews, conflicts, and backups

Writes to live files require a server-generated preview token, valid for five
minutes and one application. Preview shows actual target paths and full current/
proposed contents. Reconfiguration invalidates an outstanding preview. All target
versions are checked before a batch begins; each file is rechecked before atomic
replacement. A stale preview returns HTTP 409 before that batch writes any files.

A batch is **not a multi-file transaction**. A later filesystem error or concurrent
edit can stop it after earlier files were saved. The response and UI identify saved
files and the failure; remaining files are not attempted. Review backups before
retrying. A narrow race with unrelated external writers remains, as in the original
instruction editor. Avoid concurrent writes from different tools.

Previous contents are saved under the target's parent:
`.agent-instructions-backups/<path-hash>/<content-sha256>.md`. The `.md` suffix is a
backup container name, including for JSON and TOML. Path hashes separate files in
the same folder. Existing Agent Instructions backup namespaces remain unchanged.
First creation has no previous content to back up. Backups are deduplicated and
not automatically pruned. MCP Manager and Agent Skills expose reviewed restoration;
Profiles/Snapshots can restore saved records, and their per-file/library backups
can also be recovered externally with the core stopped. Existing newline
conventions are retained when saving.

Library edits use content-and-path version tokens and backup the previous catalog,
including on record deletion. Duplicate new IDs are rejected; select an existing
record to edit it. A library holds up to 100 records, 20 short tags per record, and
1 MiB of serialized UTF-8 data overall. Each live file is limited to 1 MiB.

Linked files/directories (including junctions), unsupported encodings, invalid
target IDs and traversal are rejected. Windows custom ACLs and alternate streams
are not explicitly copied by atomic replacement. Skill editing covers only
`SKILL.md`; supporting files are neither copied nor executed.

## API overview

All tools expose `GET state`. Profiles, Prompt Library and Snapshots expose
`POST record` and `DELETE record`, with `version` from `state.library`. Editing an
existing ID additionally requires `replace: true`.

Profiles/Snapshots preview bodies contain `id`, `libraryVersion`, and `selected`
file IDs. MCP/Skills preview bodies contain `id`, the last-read file `version`, and
`content`. Only a new, absent skill may use `version: null`. `POST apply` takes
the returned `token`. MCP Manager also accepts per-server previews with `operation` (`upsert` or `delete`), `source`, `sourceVersion`, `originalName`, `name`, `definition`, `targets` (agent IDs and file versions), and optional `replaceExisting`. It translates supported fields for each target and preserves unrelated entries. Delete is scoped to the source agent. MCP/Skills also expose `GET backups?id=...` and
`POST restore-preview` with `id`, `version`, and `backup`.

Diagnostics has no mutation routes. Requests cannot choose arbitrary filesystem
paths; configured slots and bounded skills roots determine the targets.

## Format references

Verified against official documentation on 2026-10-15:

- [Codex MCP configuration](https://developers.openai.com/codex/mcp)
- [Codex skills locations and layout](https://learn.chatgpt.com/docs/customization/overview#skills)
- [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp)
- [Claude Code skills](https://code.claude.com/docs/en/skills)

MCP adapters currently cover Claude Code and Codex only. Skill folders can be
pointed elsewhere, but the plugin does not claim automatic discovery support for
every agent or manage vendor plugin caches.

## Embedded layout (0.6.1)

The six suite pages follow ECPA’s Local Clients layout, with charcoal panels and blue selection accents. About/help and previous file versions can be expanded as needed; the main editor scales with viewport height. Left navigation remains beside the editor above 650px, including short embedded views. On narrower screens the item list stacks above the editor as a bounded vertical list. Forms, previews, paths and actions wrap without horizontal page overflow. Agent headings, file targets, diagnostics and change previews use local embedded product icons with friendly names. All seven tools include unique SVG artwork; no icon request is needed to render the editor itself.

Agent Instructions switches to an icon-bearing agent/file selector inside an iframe or a narrow/short viewport. The full grouped navigation remains available on larger standalone pages.

Browser validation covers real-core save/preview/restore workflows and 1000, 820 and 375px iframe widths at 560px height. Use `tests/embedded-layout-check.js` in a same-origin test host containing an unlocked editor iframe to repeat layout checks. Do not run workflow tests against real user files.

`tests/reference-layout.cjs` runs these checks at 560px and 800px heights, verifies that desktop sidebars remain beside the editor, captures screenshots, and runs the existing browser workflows for all seven plugins. It uses Playwright with Edge (`PLAYWRIGHT_MODULE` can point to an installed module) and an isolated same-origin proxy host at `PLUGIN_PREVIEW_URL` (default `http://127.0.0.1:58610`). Screenshots go to `dist/screenshots` or `PLUGIN_SCREENSHOT_DIR`.
