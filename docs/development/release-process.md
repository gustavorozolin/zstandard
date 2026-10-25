# Release Process

All ten packages share one stable `MAJOR.MINOR.PATCH` version. Copilot owns
issue admission, managed branches, production promotion, tags, release
receipts and reconciliation. The package workflows supply build, test and
pub.dev publication steps. Do not create a competing branch or merge flow.

## Prerequisites

- Configure automated publishing for **each** package on pub.dev: repository
  `vypdev/zstandard`, tag pattern `v{{version}}`, required environment `pub.dev`.
  These settings are private to package administration; a successful public
  API lookup does not prove that publishing is authorized.
- Protect the GitHub `pub.dev` environment with a maintainer reviewer and a
  tag-only `v*` deployment policy. There is no persistent pub token.
- Require PRs and `Pull Request Safety Gate` on `master` and `develop`, with
  deletion/non-fast-forward protection. Retain merge commits for Copilot's
  production-lineage reconciliation. Do not apply a blanket deletion ban to
  managed branches: Copilot owns their final cleanup.
- Protect stable version tags against update/deletion. Tag creation remains
  available to the authorized Copilot publisher.
- Keep installed Copilot credentials, workflows, Variables and branch ownership
  intact. Allow Actions to create PRs. Bot-created PR checks may need a
  maintainer to select **Approve workflows to run**.
- Ensure trusted Linux, Apple Silicon and Windows runners are available with
  build dependencies. Product jobs provision Flutter 3.47.2.

## Choose the release version

Use the installed Release form and select a version appropriate to the actual
compatibility changes. Published 1.5.0 accepted Dart `^3.6.0` and Flutter
`>=3.3.0`; the current main package requires Dart `^3.12.0` and Flutter
`>=3.44.0`. Review and announce these requirements before choosing a patch,
minor or major. Release-system maintenance does not itself bump versions.

## Prepare and promote

1. Open a Release issue with all installed fields. A maintainer adds
   `in-progress`; wait for the exact linked `release/X.Y.Z` and `branched`.
2. Once explicitly authorized to start the release, use the installed `deploy`
   launcher. Copilot dispatches `release_workflow.yml` in `prepare` mode.
   Do not dispatch publication or create a tag manually.
3. Preparation updates versions, CLI version, changelogs, SwiftPM pins and
   podspecs, then regenerates all four Web artifacts from canonical C source
   with the pinned Emscripten toolchain.
4. Native jobs build macOS universal, Linux x64/arm64 and Windows x64/arm64
   libraries. Every job consumes the preceding job's exact commit. Unchanged
   outputs can be retried; a moved remote rejects a push.
5. All candidate tests check out the final native-build commit. Static,
   formatting, package, platform release-build and integration gates must pass.
   The final gate rejects a moved release tip and uploads
   `release-candidate-X.Y.Z`, recording commit/tree, issue and run/attempt.
6. Only then does `prepare_deployment_action` open Copilot's normal production
   promotion PR. Complete its protected checks/review process. Do not change
   the frozen source after promotion has been recorded.

Reconcile production fixes into development before cutting a candidate.
Publication rejects a production merge whose Git tree differs from the tested
candidate, preventing untested changes from entering through the production base.

## Publish and reconcile

After promotion merges, Copilot's installed continuation dispatches `publish`
mode with its durable operation ID. Copilot creates/verifies `vX.Y.Z` at the
accepted production SHA. That immutable tag starts **Publish Tagged Release**;
the issue remains in publication until the package workflow finishes.

Before requesting pub.dev credentials, the tag workflow verifies:

- tag identity, candidate ancestry and production acceptance;
- the exact promotion PR and its unique Copilot operation marker;
- the issue's durable source SHA, production SHA and publication phase;
- a successful preparation run and its unexpired artifact for the exact
  candidate, issue and workflow attempt; and
- identical tested/production trees, metadata and synchronized artifacts.

The `pub.dev` environment requires maintainer approval. OIDC publishing then
proceeds in dependency order:

```text
zstandard_platform_interface → zstandard_native
  → zstandard_android → zstandard_ios → zstandard_linux
  → zstandard_macos → zstandard_web → zstandard_windows
  → zstandard_cli → zstandard
```

Each unpublished package must pass `dart pub publish --dry-run`, and the
workflow waits for indexing between packages. Only after all ten versions are
independently verified does Copilot create/verify the GitHub Release, receive
the checksum attachment and run `published_deployment_action`. Copilot then
performs its configured protected reconciliation. The old independent
**Integrate Published Release** workflow is retired.

## Recovery and hotfix compatibility

Before a candidate is frozen, fix the managed branch and rerun preparation.
After promotion is recorded, use Copilot's control center and recovery actions.
Publication recovery retries a failed workflow for the existing tag without
moving it. The tag workflow can also be rerun directly after inspecting the
failure. Published versions are skipped; reconciliation starts only after all
ten packages are verified.

Evidence is retained for 90 days. Missing, expired or mismatched evidence
blocks publication and cannot be replaced by an operator assertion. Prepare a
new candidate/version when an old frozen operation cannot be verified.
Incorrect published content requires a new version; never overwrite pub.dev.

The installed hotfix workflow is unchanged. Accepted hotfix tags retain its
GitHub-only contract and do not enter the package publisher. A GitHub hotfix
Release is not evidence of ten-package publication.

See the [deployment runbook](../deployment/RUNBOOK.md) and [CI/CD](ci-cd.md).
