# Go provider plugins

Claude Remote Login and Z.ai Provider are maintained source adaptations, kept under `plugins/` alongside the Rust plugins. They use `plugin.toml` for independent versions and repositories. Their source provenance and upstream licences are recorded in each directory.

## Toolchain

Use Go **1.27.3** and Zig **0.14.1** for Windows amd64. Set `ECPA_GO` to the full go.exe path and `CC` to a C compiler command if they are not on PATH. Locally, `scripts/go_build.py` also recognises `test-artifacts/toolchains/go/bin/go.exe` and `test-artifacts/toolchains/zig-x86_64-windows-0.14.1/zig.exe`.

Official archives used for this release:

- https://go.dev/dl/go1.27.3.windows-amd64.zip — SHA-256 `f26081f438319757f8a1b46d7d0b2c5ec7583d4038e485e0aa725cfde7885fff`
- https://ziglang.org/download/0.14.1/zig-x86_64-windows-0.14.1.zip — SHA-256 `554f5378228923ffd558eac35e21af020c73789d87afeabf4bfd16f2e6feed2c`

Z.ai’s vendored YAML v3.0.1 and CPA v8.0.42 SDK files were compared byte-for-byte with their published Go module archives before adaptation. Dependencies are not downloaded during build: GOPROXY and GOSUMDB are off, GOTOOLCHAIN is local, and vendoring is enforced where applicable.

Run `python scripts/setup_go.py` to download and verify those archives into the ignored local toolchain directory. Existing local toolchains are reused; this is not a system installation.

## Verify and package

Run `python scripts/check_go.py` (format, race detector and vet for both Go plugins), then `python scripts/validate.py` and the release-tool tests. `python scripts/package.py --plugin <id>` builds a Windows DLL into `target/go/`, packages licences/security notes and creates checksums and release metadata. Source archives remain the complete shared workspace.

`python tests/provider_plugins.py --core C:/path/to/cli-proxy-api.exe` builds fixture DLLs into `target/go-fixture/`, then runs an isolated core with a temporary auth directory. It never modifies production configuration or accounts. Do not publish fixture DLLs. Release packaging uses an explicit empty GOFLAGS, and rejects binaries built with the fixture tag.

Real-provider login and inference checks require the account owner’s explicit participation and remain unverified until performed. An automated test pass is not proof of provider billing rules or account eligibility.

The Windows race test executable has ASLR disabled because Go’s ThreadSanitizer requires a fixed address layout and Zig 0.14 does not accept the GNU linker flags Go uses for it. `check_go.py` changes only test executable PE flags under `target/go-tests/`. Production DLLs keep ASLR enabled.

For Zig race tests, the check script also builds a synchronization import archive
from the pinned Zig distribution's Windows API definition under `target/go-tests`.
This avoids depending on a hosted runner's incidental MinGW library search paths.
It is test-only and does not modify the toolchain or release DLLs. Git attributes
keep Go sources in LF format on Windows so clean checkouts pass `gofmt`.
