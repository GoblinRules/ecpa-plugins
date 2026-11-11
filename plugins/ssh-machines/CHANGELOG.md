# Changelog

## 0.2.0

- Share verified machine operations with the gateway helper; bind identity contents and host pin; require per-request approval for named service restarts.
- Existing local profiles and credentials are preserved; no automatic remote deployment.

## 0.1.0

- Add a machine inventory and three-step setup wizard.
- Select an existing key or a single SSH-agent identity; require independent host-key fingerprint confirmation.
- Provide bounded read-only connection diagnostics and an interactive terminal command for the operator.
- Add private profile import/export, conflict detection and a previous-version backup.
- Keep SSH reachability separate from runner registration and agent execution permissions.
