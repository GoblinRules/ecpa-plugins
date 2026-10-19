# Changelog

## 0.1.0

- Named Cloudflare and GitHub connections with Windows Credential Manager storage.
- Account identity verification without returning tokens to the editor or catalogue.
- Project assignments with nearest-parent resolution and stale-edit protection.
- CLI/MCP launcher with concurrent account isolation, stdio and exit-code forwarding.
- Token-free PowerShell, Claude JSON and Codex TOML configuration generation.
- Windows x64 plugin and separately checksummed helper executable.

Validated with synthetic credentials against CLIProxyAPI 8.0.32, Windows Credential Manager and Edge at 1200, 820 and 480px. Real account verification and deployment require your own scoped tokens and were not performed during development.
