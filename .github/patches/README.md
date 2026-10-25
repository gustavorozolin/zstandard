# Flutter iOS log readiness backport

`flutter-ios-log-readiness.patch` backports Flutter's official fix and its three
regression tests from commit `c3ed85ef987759ee54a6bce275490cde2a238dc1`
([flutter/flutter#193142](https://github.com/flutter/flutter/pull/193142)).
The first hunk's unchanged context is shortened to fit stable 3.47.2, and the
test fixture omits the newer simulator constructor's `cpuArch` argument.
The production Dart change is identical to upstream. Flutter's source and
tests retain their existing BSD license headers.

The simulator log stream must deliver its readiness header before Flutter
launches the test app. Otherwise it can miss the app's one-time VM service URL
and wait indefinitely after a successful build (flutter/flutter#181771).

The setup script accepts only the reviewed Flutter 3.47.2 commit
`d3b14c876900e553bc736ca19295fc09e3853e8e`. It patches a job-owned SDK copy,
rebuilds that copy's tool snapshot on its next invocation and leaves the shared
SDK unchanged. The original tests and the 900-second integration limit remain.
CI runs the upstream delayed-log-stream regression tests against the patched
SDK. Remove this backport when the selected stable SDK includes the fix.
