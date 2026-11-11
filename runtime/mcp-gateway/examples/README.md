# Reference-only profile templates

Copy a template, replace non-secret placeholders and secret UUIDs, and import it
in Connections Manager. Every template starts disabled. No executable downloads,
paid service calls, deployments or credentials are included. A hosted endpoint
must actually implement Streamable HTTP MCP; a plain REST base URL is not an MCP.

`sample.json` runs without external setup. Portainer uses the bundled helper.
Cloudflare and Runway use built-in fixed API adapters. Cloudflare optionally enables
approval-bound Wrangler jobs with installed Node/Wrangler paths. Provider API keys
route through CLIProxyAPI, not MCP. SSH selects a verified machine catalogue entry.
Replace placeholder IDs/model names locally; API keys and OAuth are not interchangeable. `runtime-workspaces.example.json` is a fragment to review/merge
into runtime settings, not a second runtime config or a remote executor.
