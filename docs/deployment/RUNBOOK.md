# Deployment and Recovery Runbook

## Release readiness without publication

1. Verify all ten packages' pub.dev Admin settings: repository
   `vypdev/zstandard`, tag pattern `v{{version}}`, required environment `pub.dev`.
   An uploader or publisher admin must verify these private settings.
2. Verify `pub.dev` has a maintainer reviewer and only the `v*` tag policy.
3. Verify active `master`/`develop` protection requires `Pull Request Safety
   Gate` and prevents deletion/non-fast-forward updates. Keep merge commits and
   Copilot's managed branch lifecycle available.
4. Verify stable tags cannot change or be deleted, installed Copilot credentials
   are healthy, and trusted Linux/macOS/Windows runners are online.
5. Run release contract tests, metadata checks and PR platform CI. No tag or
   registry credential is needed for these checks.
6. Review SDK compatibility and choose the release type in a separate Release
   issue. Maintenance changes do not authorize deployment.

Do not add `deploy`, create tags/releases or run publication to test readiness.
Publishing to pub.dev is immutable and is not a readiness test.

## Authorized release

Use the installed Release form, add `in-progress` as a maintainer and wait for
Copilot's linked branch and readiness label. Once deployment is explicitly
authorized, its launcher starts preparation. Follow the issue's control center
through candidate validation and the production promotion PR.

All platform jobs validate one exact candidate. Its commit/tree evidence is
uploaded before promotion is delegated to Copilot. After the protected PR
merges, Copilot tags the accepted production SHA. Do not manually tag the
release tip: production and candidate commits can differ while their tested
content must be identical.

The tag publisher verifies Copilot state, promotion ownership, successful CI
evidence and metadata before reaching the protected `pub.dev` environment.
Approve that environment after reviewing the accepted candidate. Publication
uses GitHub OIDC; no persistent pub token is required.

After public verification of all ten packages, the product workflow delegates
GitHub Release creation and reconciliation to installed Copilot actions. Do not
create independent integration PRs or delete managed branches yourself.

## Recovery

- Preparation failure before promotion: fix the linked branch and rerun.
  Native commit steps accept unchanged rebuilt outputs.
- Remote tip moved: preparation stops rather than silently testing a newer
  commit. Inspect the concurrent change and start a consistent candidate attempt.
- Production content differs: reconcile the production change before preparing
  a new candidate; do not bypass evidence validation.
- Publication interrupted or indexing delayed: inspect the issue failure and
  retry its publication action or the same tag workflow. Already public package
  versions are safely skipped.
- Existing tag on recovery: the continuation retries its failed publication
  workflow, preserving the tag and operation identity.
- GitHub Release/checksum finalization failed: rerun the same tag workflow.
  Existing packages are reused; Copilot verifies its release receipt.
- Expired evidence: publication stops. Retention is 90 days; plan a new verified
  candidate/version rather than fabricating a replacement attestation.
- Incorrect published content: prepare a new version. Never move a stable tag
  or attempt to overwrite a published package.

Hotfixes retain their existing Copilot GitHub-only publication contract and do
not implicitly publish packages to pub.dev.

## Updating upstream zstd

`scripts/update_zstd.sh` defaults to the pinned upstream commit. For an
intentional upgrade, review the diff, update `zstandard_native/UPSTREAM_ZSTD.md`,
regenerate bindings if the public header changed, regenerate WebAssembly and
rerun every platform gate. Apple CocoaPods sync scripts create ignored
compatibility copies; SwiftPM uses the canonical repository target directly.

See [Release process](../development/release-process.md) and
[`SECURITY.md`](../../SECURITY.md).
