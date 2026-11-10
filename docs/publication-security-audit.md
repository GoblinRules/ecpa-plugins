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

## Repeating checks

Run `scripts/publication_guard.py` before committing/publishing. It inspects the
tracked source boundary and release assets for private-file names and local build
paths, without printing matching data. Run Gitleaks on source Git history and a
clean source snapshot with `.gitleaks.toml`; keep reports outside tracked files.
The guard is a focused privacy check, not a substitute for a full secret scanner.

New releases must record their actual source commit. Do not upload a local data
directory or a workspace ZIP made by indiscriminate recursive archiving. Release
source archives must use `git archive` of the audited commit.
