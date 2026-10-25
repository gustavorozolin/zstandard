# Flutter on shared runners

The composite installs the requested stable SDK for the runner architecture in
the versioned `zstandard-flutter-v2` tool cache. Linux jobs use the `vypdev` group
with `self-hosted, codex, Linux`; Apple jobs use `self-hosted, macOS, ARM64`.
Windows jobs use the separate `setup-flutter-windows` action, which selects Git
Bash and verifies its downloaded jq executable.

The SDK stays in each persistent runner's versioned tool directory. Setup reuses
that installation and downloads it only when missing. GitHub's remote SDK cache
is disabled: transferring multi-gigabyte archives delayed setup and post-job
cleanup enough to threaten CI deadlines on the shared Apple runners. Pub's
existing local cache and the requested SDK version/architecture are preserved.

On Unix, subsequent `flutter` commands use a job-owned settings profile through
a private launcher. SwiftPM/CocoaPods selection therefore cannot overwrite the
operator's Flutter settings or another runner's selection. The existing pub
cache remains explicit; SDK files, the parent HOME and global Git configuration
are not replaced. Standalone `dart` publishing keeps its workflow-owned
credential configuration.

Apple integration tests require Xcode and an installed iOS runtime. CI creates
and removes only its own simulator UUID. Setup does not install Xcode or accept
Apple agreements. The reconciliation keeps develop's existing test matrices,
coverage thresholds and complete package publication workflow.

The iOS integration and release-candidate jobs additionally use a disposable
copy of Flutter 3.47.2 with the official simulator log-readiness fix backported
from flutter/flutter#193142. The SDK in the shared tool cache is unchanged.
The job's existing launcher selects the private copy through `FLUTTER_ROOT`,
and cleanup removes only that job's marked directory. See
[`../../patches/README.md`](../../patches/README.md) for provenance and removal.

The Linux dependency action reuses installed packages and downloads missing
packages into a private prefix with their dependency closure. It never runs
sudo, package maintainer scripts, dpkg repair or host package installation.
Headers, libraries and pkg-config metadata combine that prefix with read-only
links to the installed toolchain. The host package database remains unchanged.

Web jobs select the private browser dependency set. Chrome for Testing and its
matching driver are downloaded without sudo or host dependency installation.
The rootless contract also launches the real downloaded browser and verifies
its page content; a version-only check is insufficient.
The two-case native contract covers Ubuntu 22.04 and 24.04. Browser libraries
reuse installed packages or select the available time64/legacy names from
private APT indexes, including private binary caches. Both versions must compile
GTK and AArch64 probes, execute LCOV and launch Chrome without changing host dpkg.

Android profiles export runtime tool paths without host header/library
search variables that would override the NDK sysroot. The mixed x86_64/AArch64
release job retains private native metadata and clears those variables only
for the cross build, preserving the AArch64 compiler sysroot. WebAssembly
regeneration uses the same isolation for Emscripten.
