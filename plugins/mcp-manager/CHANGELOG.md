# Changelog

## 0.7.0

- Dedicated server manager with agent icons, searchable server lists and configuration/advanced JSON editing.
- Add, duplicate, rename and remove individual servers while retaining unrelated servers and agent settings.
- Explicit assignment to Claude Code, Codex or both; translate stdio and Streamable HTTP settings between their formats.
- Block unsupported cross-client fields and require explicit replacement of conflicting same-name definitions.
- Mask environment variable and header values in forms; retain full-file previews, stale-file checks, backups and reviewed restore.
- Keep custom configuration paths and existing files; no migration or process execution.

Verification: 19 Rust tests, strict Clippy and formatting, isolated real-core API tests, browser CRUD/assignment/translation/restore-preview workflows, and embedded layout checks at 1000/820/375px widths and 560/800px heights.
