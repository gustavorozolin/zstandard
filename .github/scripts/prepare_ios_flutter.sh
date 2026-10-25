#!/usr/bin/env bash
# Backport flutter/flutter#193142 into a disposable SDK, never the shared SDK.
set -euo pipefail

task_temp="$(cd "${RUNNER_TEMP:?RUNNER_TEMP is required}" && pwd -P)"
expected_revision=d3b14c876900e553bc736ca19295fc09e3853e8e

if [[ "${1:-}" == --cleanup ]]; then
  owned="${ZSTANDARD_IOS_FLUTTER_DIR:?The owned SDK directory is required}"
  if [[ "${owned%/*}" != "$task_temp" ||
        "${owned##*/}" != zstandard-ios-flutter.* ||
        -L "$owned" || ! -f "$owned/.zstandard-ios-flutter" ]]; then
    echo 'Refusing to remove a directory not owned by this iOS SDK job.' >&2
    exit 1
  fi
  if [[ "$(cat "$owned/.zstandard-ios-flutter")" != "$expected_revision" ]]; then
    echo 'Refusing to remove an iOS SDK directory with an unknown marker.' >&2
    exit 1
  fi
  rm -rf -- "$owned" || exit 1
  exit 0
fi

sdk="$(cd "${FLUTTER_ROOT:?FLUTTER_ROOT is required}" && pwd -P)"
[[ "$(git -C "$sdk" rev-parse HEAD)" == "$expected_revision" ]] || {
  echo 'Review the iOS log-readiness backport before changing the Flutter SDK.' >&2
  exit 1
}
git -C "$sdk" diff --exit-code HEAD -- \
  packages/flutter_tools/lib/src/ios/simulators.dart \
  packages/flutter_tools/test/general.shard/ios/simulators_test.dart || exit 1

owned="$(mktemp -d "$task_temp/zstandard-ios-flutter.XXXXXX")"
printf '%s\n' "$expected_revision" > "$owned/.zstandard-ios-flutter"
# Record ownership before copying so failures can also clean up their own SDK.
printf 'ZSTANDARD_IOS_FLUTTER_DIR=%s\n' "$owned" >> "${GITHUB_ENV:?GITHUB_ENV is required}"

case "$(uname -s)" in
  Darwin) cp -cR "$sdk" "$owned/flutter" || exit 1 ;;
  Linux) cp --reflink=auto -R "$sdk" "$owned/flutter" || exit 1 ;;
  *) echo 'The iOS backport requires a macOS or Linux verification runner.' >&2; exit 1 ;;
esac

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
backport="$repository/.github/patches/flutter-ios-log-readiness.patch"
git -C "$owned/flutter" apply --check "$backport" || exit 1
git -C "$owned/flutter" apply "$backport" || exit 1
# The copied snapshot predates the patched source. Invalidate only this copy.
rm -f "$owned/flutter/bin/cache/flutter_tools.snapshot" \
  "$owned/flutter/bin/cache/flutter_tools.stamp"
git -C "$sdk" diff --exit-code HEAD -- \
  packages/flutter_tools/lib/src/ios/simulators.dart \
  packages/flutter_tools/test/general.shard/ios/simulators_test.dart || exit 1
printf 'FLUTTER_ROOT=%s\n' "$owned/flutter" >> "$GITHUB_ENV"
printf 'Prepared private iOS Flutter SDK: %s\n' "$owned/flutter"
