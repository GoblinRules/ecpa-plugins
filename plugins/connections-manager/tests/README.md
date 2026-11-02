# Connections Manager checks

Run the Rust tests, `python scripts/package.py --plugin connections-manager`, and `integration.py --core <official-core-executable>` from the workspace root. These use only temporary directories and synthetic vault credentials.

For browser verification run the integration script with `--serve`, then set `CONNECTIONS_BASE` to its printed base URL and run `node plugins/connections-manager/tests/browser.cjs`. `PLAYWRIGHT_MODULE` may point to an existing Playwright installation. Windows uses Edge. This is the repository's native-core browser workflow.

The integration fixture also exercises Portainer through a synthetic HTTP server and the real helper: verification, MCP initialization, four GET-only tools, metadata filtering, framed logs and invalid request rejection. No production access token is used.

Integration checks exercise automatic helper installation in an isolated `LOCALAPPDATA`, tamper detection/repair, route authentication and self-launch rejection. Unit tests cover locked-destination and competing-installer failures preserving the old executable. The browser checks cover managed helper defaults, account-specific MCP names and invalid configuration rejection.

Use `--browser` on `integration.py` to run the browser checks inside the same fixture and clean up automatically. Install Playwright locally and set `PLAYWRIGHT_MODULE` if it is outside Node’s module search path.
