# Public repository and release audit

Audit date: 2026-11-10. This records the scope and limitations of the publication
check; it is not a certification that arbitrary future code, dependencies or
remote services are safe.

## Existing public material

Checked all reachable Git history of the source repository and ten dedicated
release repositories. Downloaded and inspected 130 published assets across those
repositories, including historical binary/source archives. Examined 408 unique
archive/member payloads, including printable binary strings. The offline scanner
was Gitleaks 8.30.1, downloaded from its official release and checksum-verified.

No confirmed live service credentials or private keys were found in this scope.
The one scanner finding was the fixed synthetic OAuth state in the Z.ai contract
test. An exact-value/path exception documents that fixture; it does not exclude
the test file or test directories from secret scanning.

The privacy scan also checked supplied private endpoints, Tailscale hostnames and
the pilot secret reference. It found **personal compiler build paths in historical
Windows binaries**. Those paths reveal a local Windows username/checkout location;
they are not authentication credentials. Source history had a generic connection
label matching a supplied label, but no corresponding real endpoint or credential.
That example is now named `portainer-demo` to avoid ambiguity.

## Remediation and publication boundary

Release packaging remaps developer home and checkout paths to neutral build paths.
Affected current Rust plugins receive patch releases, independently versioned.
Connections Manager's new gateway release and the new SSH plugin use the same
sanitized packaging. A build-path check must pass before a new binary is uploaded.

Real catalogues, machine exports, bootstrap tokens, OAuth state, runtime logs,
backups and local handover reports remain outside tracked source/release archives.
Gateway templates use dummy UUIDs/endpoints and contain no live machine profiles.
Exports containing machine/account metadata are **private configuration**, even
when they contain only credential references; they are not publication inputs.

The local audit reports intentionally remain ignored. Public documentation reports
finding categories rather than reproducing private paths or values. Git metadata
(author identities and public repository URLs) is expected public project metadata.

Historical assets are handled separately from clean replacement releases. Replacing
a current release cannot erase prior downloads or mirrors. Removing an old binary
download does not revoke any credential; if a real key is ever found, revoke/rotate
it first and then handle history/caches explicitly. No broad history rewrite is
performed merely to hide compiler paths.

Clean replacements are now published: Connections Manager 0.7.0, MCP Manager
0.7.1, the six other affected existing Rust plugins at 0.6.4, and SSH & Machines
0.1.0. All nine releases were downloaded anonymously and verified against the
local SHA-256 hashes, source revision and publication guard. The complete source
snapshot and printable strings from all nine current plugin binaries also passed
the secret scan. The two Go plugins remain at 1.1.0; their audited binaries did
not need this packaging change. All eleven dedicated repositories have updated
documentation. With the owner's approval, all **48 affected historical binary
downloads** were removed after verifying the replacements. A subsequent check
confirmed that exactly those asset IDs were removed and all other historical
assets, release notes and tags were preserved. Source archives and Git history
remain available. Previously downloaded copies and third-party caches cannot be
recalled; the new builds do not retroactively sanitize those copies.

## Repeating checks

Run `scripts/publication_guard.py` before committing/publishing. It inspects the
tracked source boundary and release assets for private-file names and local build
paths, without printing matching data. Run Gitleaks on source Git history and a
clean source snapshot with `.gitleaks.toml`; keep reports outside tracked files.
The guard is a focused privacy check, not a substitute for a full secret scanner.

New releases must record their actual source commit. Do not upload a local data
directory or a workspace ZIP made by indiscriminate recursive archiving. Release
source archives must use `git archive` of the audited commit.
