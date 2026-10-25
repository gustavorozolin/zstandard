# CI/CD

## Pull requests

`pull_request.yml` is the untrusted-code safety gate. It runs on GitHub-hosted
Ubuntu with read-only contents permission, resolves monorepo dependencies,
formats and analyzes all ten packages, executes every available VM/unit test,
and validates metadata, generated Web artifacts, and shell syntax. A required
hosted matrix collects coverage for the CLI, platform interface, and main
package on every pull-request head, enforces their package-specific thresholds,
and uploads the three matching Codecov flags for trusted same-repository pull
requests. Forks run the same coverage gates without receiving the upload token.
Its final
`Pull Request Safety Gate` job is the stable required-check context; repository
rules should require that one context on both `master` and `develop` rather
than coupling protection to individual matrix-entry names.

Untrusted pull-request code is never sent to persistent self-hosted runners.
The platform-heavy workflows (`pr_check_*.yml`, retained under their historic
names) run only on trusted pushes to `develop` or by explicit manual dispatch.
They provide Android emulator/instrumentation, Linux desktop, ChromeDriver,
Windows desktop/native, and both SwiftPM and CocoaPods Apple integration. They
also run publish dry-runs and coverage where applicable.

Every third-party action reference is pinned to a full commit SHA. Copilot
automation uses `pull_request_target` or issue metadata without checking out
untrusted pull-request code, grants read-only repository contents, and only
uses its PAT for OWNER, MEMBER, or COLLABORATOR actors.

## Release workflows

`release_workflow.yml` retains Copilot's `prepare`, `publish` and `resume`
contract. Preparation consumes an admitted managed release branch, generates
metadata/native artifacts and runs all candidate gates on one exact commit.
It uploads a commit/tree receipt and invokes Copilot's production promotion.
After protected promotion, Copilot's publication continuation creates/verifies
the accepted production tag. Failed tag publications are retried without
moving that tag.

`publish_workflow.yml` runs only on stable version tag pushes. Before OIDC it
requires a successful candidate run/attempt, its artifact, identical tested and
production content, and the matching Copilot promotion/issue state. The
protected `pub.dev` environment requires maintainer approval. After publishing
and independently verifying all ten packages, the installed Copilot actions
create/verify the GitHub Release and start configured reconciliation. Accepted
hotfixes preserve their existing GitHub-only lane.

Copilot state transitions share its per-issue non-cancelling queue. Package
publication has a separate repository-wide lock, so waiting for environment
approval cannot deadlock a Copilot continuation. The former standalone
integration workflow is retired; Copilot owns reconciliation and cleanup.

The package preparation contract runs real version/metadata helpers, actual
CMake path resolution, Git commit/retry scenarios, admission scripts and
candidate evidence validation using isolated fixtures. These tests never call
a publication API. See [Release process](release-process.md).

## Runner trust and requirements

Self-hosted Linux, Windows, and macOS runners are persistent trusted release
infrastructure. They must not be exposed to fork pull requests. Linux needs
the native/GTK toolchain, Android SDK/Java 17, Chrome, and optional AArch64
cross-tools. Windows needs Visual Studio C++/CMake and an interactive desktop.
Apple needs Xcode, simulator runtimes, CocoaPods, and a logged-in WindowServer
session for macOS integration.

The local composite actions verify the pinned Flutter 3.47.2 toolchain.
Platform workflows build release candidates as well as debug test hosts;
missing infrastructure is a failure rather than a silent skip.

## Local equivalents

Use `dart scripts/create_local_overrides.dart <package>` before resolving an
individual monorepo package; the `.sh` wrapper remains available on Unix-like
systems. Run `dart format --output=none
--set-exit-if-changed .`, the appropriate analyzer/test command, and the
platform integration script. `scripts/check_pub_metadata.dart` validates the
publication contract; `scripts/build_web_wasm.sh` regenerates Web artifacts.

See [Testing](testing.md), [Self-hosted CI](self-hosted-ci.md), and
[Release process](release-process.md).

### Self-hosted Linux runner contract

The Linux workflows target the repository labels `[self-hosted, Linux]`. The runner account must be able to use passwordless `sudo` so the local composite action at [`.github/actions/setup-linux-dependencies/action.yml`](../../.github/actions/setup-linux-dependencies/action.yml) can install the required packages.

The release workflow enables the action's `arm64` option, which installs the
`aarch64-linux-gnu` cross compiler before producing the Linux ARM64 CLI
artifact; it does not rely on a manually prepared compiler on the runner.

The action installs the common native toolchain (`build-essential`, Clang, CMake, Ninja, `pkg-config`, and `curl`). Desktop jobs additionally install GTK and Xvfb; coverage jobs install `lcov` and `bc`.

Before installing anything, the action repairs an interrupted Debian package
transaction with `dpkg --configure -a` and `apt-get -f install`, then runs the
installation under a host-local lock and verifies the result with
`apt-get check`. This is required because self-hosted runners preserve their
package database between jobs; a cancelled job must not make the next check
fail before the project is even built. If recovery itself fails on a runner,
inspect `dpkg --audit` and the package-manager logs on that host.

Android runners must also provide:

- Android SDK with `platform-tools` and the emulator on the SDK path.
- Java 17. `/dev/kvm` is optional because the current workflow explicitly uses software emulation.
- Network access for the API 30 `aosp_atd` x86_64 system image used by the emulator launcher. Android ATD is intentionally used because it removes background services that are irrelevant to these tests and reduces CPU/memory pressure on the software-only runner.

The Android job builds the example APK before booting the emulator. The Linux job builds the example application before running its integration tests. The Web job installs a matching Chrome/ChromeDriver pair, builds the example, and runs the `flutter drive` integration suite under Xvfb. A missing dependency or failed build is an explicit failure; platform integration tests are not silently skipped in CI.

Android integration tests verify non-empty payloads, exact
`decompress(compress(input))` round-trips, empty input, corruption handling,
all documented compression levels, and deterministic property-based cases.
The Android instrumentation suite repeats the round-trip and invalid-frame
checks directly through JNI against the same shared library loaded by Dart
FFI. The level-22 test uses a small payload because the CI emulator is
software-only; large-content behavior is covered separately.

PR checks pin Flutter 3.47.2. This is intentional: the organisation-level `FLUTTER_VERSION` variable previously selected Flutter 3.41.4, which is below the minimum required by the current root and Android packages.

Apple workflows use the self-hosted ARM64 Mac runner and validate both native dependency managers. iOS simulators are booted through `simctl` without opening the Simulator UI; the iOS job invokes the single integration file explicitly because the example intentionally keeps all iOS checks in one test process. macOS tests run the built app in the runner's logged-in graphical session. Windows uses self-hosted X64 runners and requires a Windows desktop session plus Visual Studio/CMake for native builds and launched integration tests.

### Self-hosted Windows runner contract

Windows jobs target `[self-hosted, Windows, X64]`. The workflow installs and caches the pinned Flutter SDK on each runner, then enables Windows desktop support and verifies CMake. Each runner must provide a Visual Studio C++ desktop toolchain and an interactive desktop session because Flutter's Windows integration tests launch the compiled example application.

The Windows workflow builds and tests the implementation package from the repository and from the exact candidate in a private Pub-cache-shaped tree. Each path runs the native C++ zstd round-trip tests, Dart package tests, and launched Flutter integration tests. A separate job runs the federated `zstandard/example` application to verify the public plugin entry point on Windows.


## Unpublished API candidates

The integrity audit adds `ZstandardNativeCodec` and bounded decompression to
packages whose current published 1.5.0 versions do not contain those APIs.
All PR jobs resolve matched monorepo dependencies through the reviewed
`prepare-candidate-dependencies` action. Native matrices retain workspace
and `pub-cache` source layouts: the latter copies only tracked candidate
files into a job-private `hosted/pub.dev/zstandard_native-<version>` tree and
a separate Swift package root, then hides the workspace native package.
This tests discovery outside the checkout; it is not evidence of a new
pub.dev publication. The interface and platform dependencies remain matched
to the candidate through generated local overrides. Originals are restored
from this job's private backup after native checks.

Seven filesystem regression tests cover 14 distinct inputs: workspace and
private-cache success, four invalid source values, missing CI output, five
malformed versions, tracked source drift and an escaping tracked symlink.
They exercise the actual Dart staging helper. The platform matrices continue
to build and launch their real native hosts; these fixtures replace none of
those checks. Release preparation updates all package versions and minimum
inter-package dependencies together before any immutable tag or publication.
