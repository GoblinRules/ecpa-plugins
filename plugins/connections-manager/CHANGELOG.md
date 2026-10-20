# Changelog

## 0.5.0

- Four-step connection wizard with service-specific authentication and fields.
- Tool and output choices filtered by selected account/project; stale output cleared when switching.
- Shared helper Settings: one executable for all connections, browser-local path persistence and a Verify helper button.
- Helper diagnostics checks executable identity and version without opening a terminal window.
- Updated helper required for verification; existing credentials and accounts remain compatible.

## 0.4.0

- Portainer connections with server URL validation and Windows vault access-token storage.
- Authenticated verification against accessible environments.
- Built-in stdio MCP with read-only environments, stacks, Docker containers and bounded logs.
- Portainer preset generates Claude/Codex configuration without another server package.
- Reject redirects, write tools, path injection and unsafe URL changes; filter sensitive metadata.
- Update both the plugin and helper. Real authenticated Portainer access requires your locally entered token.

## 0.3.0

- Reuse existing GitHub CLI logins through an interactive account picker, without browser sign-in.
- Verify the selected identity before securely importing a credential copy.
- Preserve the source CLI profile and active account; ignore competing inherited tokens.
- Add tests for account selection, missing logins, identity mismatch, cancellation and generated commands.
- Update both the plugin and helper to use this feature.

## 0.2.0

- Guided account onboarding, helpful empty project state and explicit tool/MCP choices.
- Isolated GitHub CLI browser login, verified username confirmation and Windows vault import.
- Prevent generating MCP configuration for ordinary GitHub CLI or Wrangler commands.
- Explain agent inheritance and the current Wrangler/remote MCP OAuth limitations.
- Update both the plugin and the separately downloaded helper for GitHub sign-in.

## 0.1.0

- Named Cloudflare and GitHub connections with Windows Credential Manager storage.
- Account identity verification without returning tokens to the editor or catalogue.
- Project assignments with nearest-parent resolution and stale-edit protection.
- CLI/MCP launcher with concurrent account isolation, stdio and exit-code forwarding.
- Token-free PowerShell, Claude JSON and Codex TOML configuration generation.
- Windows x64 plugin and separately checksummed helper executable.

Validated with synthetic credentials against CLIProxyAPI 8.0.32, Windows Credential Manager and Edge at 1200, 820 and 480px. Real account verification and deployment require your own scoped tokens and were not performed during development.
