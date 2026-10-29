"""Resolve a versioned native dependency and exercise its release FFI exports."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SWIFT = shutil.which('swift')


@unittest.skipUnless(sys.platform == 'darwin' and SWIFT, 'macOS and Swift are required')
class SwiftPMNativeDependencyTests(unittest.TestCase):
    def test_versioned_release_retains_ffi_symbols(self):
        with tempfile.TemporaryDirectory(prefix='zstandard-swiftpm-') as temporary:
            stage = Path(temporary).resolve()
            native = stage / 'native'
            native.mkdir()
            shutil.copy2(ROOT / 'Package.swift', native / 'Package.swift')
            for relative in ('zstandard_native/src/zstd', 'zstandard_native/apple'):
                shutil.copytree(ROOT / relative, native / relative)

            environment = {**os.environ, 'CLANG_MODULE_CACHE_PATH': str(stage / 'modules')}

            def run(command, cwd):
                result = subprocess.run(command, cwd=cwd, env=environment,
                                        capture_output=True, text=True, timeout=180)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout.strip()

            git = ['git', '-c', 'user.name=SwiftPM test',
                   '-c', 'user.email=swiftpm-test@localhost',
                   '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false',
                   '-c', 'core.hooksPath=/dev/null']
            for arguments in (['init', '-q'], ['add', '.'],
                              ['commit', '-qm', 'Native candidate'], ['tag', '1.0.0']):
                run(git + arguments, native)

            consumer = stage / 'consumer'
            source = consumer / 'Sources/Probe'
            source.mkdir(parents=True)
            (consumer / 'Package.swift').write_text('''// swift-tools-version: 5.9
import PackageDescription
let package = Package(
    name: "Probe",
    platforms: [.macOS(.v10_15)],
    dependencies: [.package(url: "%s", exact: "1.0.0")],
    targets: [.executableTarget(name: "Probe", dependencies: [
        .product(name: "zstandard-native", package: "native")
    ])]
)
''' % native.as_uri())
            shutil.copy2(ROOT / 'scripts/tests/fixtures/swiftpm_ffi_probe.swift',
                         source / 'main.swift')

            build = [SWIFT, 'build', '--disable-sandbox', '--manifest-cache', 'local',
                     '--scratch-path', str(stage / 'build'),
                     '--cache-path', str(stage / 'cache'),
                     '-c', 'release', '--enable-dead-strip', '-debug-info-format', 'none']
            run(build, consumer)
            binary = Path(run(build + ['--show-bin-path'], consumer)) / 'Probe'
            self.assertIn('FFI release probe passed', run([str(binary)], consumer))


if __name__ == '__main__':
    unittest.main()
