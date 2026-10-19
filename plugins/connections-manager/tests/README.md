# Connections Manager checks

Run the Rust tests, release build, and `integration.py --core <official-core-executable>` from the workspace root. These use only temporary directories and synthetic vault credentials.

For browser verification run the integration script with `--serve`, then set `CONNECTIONS_BASE` to its printed base URL and run `node plugins/connections-manager/tests/browser.cjs`. `PLAYWRIGHT_MODULE` may point to an existing Playwright installation. Windows uses Edge. This is the repository's native-core browser workflow.
