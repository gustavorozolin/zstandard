"""Real filesystem contracts for the prepublication native-package CI source."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'prepare_native_candidate.dart'
DART = shutil.which('dart')
if DART:
    # Flutter's launcher updates its SDK stamps. Use its embedded Dart executable
    # for these standalone fixtures without changing a shared SDK.
    executable = 'dart.exe' if os.name == 'nt' else 'dart'
    embedded = Path(DART).resolve().parent / 'cache/dart-sdk/bin' / executable
    if embedded.is_file():
        DART = str(embedded)


@unittest.skipUnless(DART, 'Dart SDK is required for the candidate-source contract')
class NativeCandidateSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='zstandard-candidate-test-')
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name).resolve()
        self.root = self.parent / 'repository'
        self.root.mkdir()
        self.native = self.root / 'zstandard_native'
        (self.native / 'lib').mkdir(parents=True)
        (self.native / 'pubspec.yaml').write_text('name: zstandard_native\nversion: 1.5.0\n')
        (self.native / 'lib/codec.dart').write_text('const candidateCodec = true;\n')
        (self.root / 'Package.swift').write_text('// zstandard_native/src is relative to this file\n')
        self.state = self.parent / 'runner-temp'
        self.state.mkdir()
        self.environment_file = self.parent / 'github-environment'
        self.environment_file.touch()
        self.git('init', '-q')
        self.git('add', 'zstandard_native', 'Package.swift')
        (self.native / 'untracked-sentinel').write_text('private-untracked-value')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)

    def run_source(self, source='pub-cache', *, include_environment_file=True):
        environment = {**os.environ, 'RUNNER_TEMP': str(self.state)}
        environment.pop('GITHUB_ENV', None)
        if include_environment_file:
            environment['GITHUB_ENV'] = str(self.environment_file)
        return subprocess.run([DART, str(SCRIPT), source], cwd=self.root, env=environment, capture_output=True, text=True, timeout=30)

    def exported(self):
        return dict(line.split('=', 1) for line in self.environment_file.read_text().splitlines())

    def test_workspace_keeps_sources_and_uses_the_current_candidate(self):
        result = self.run_source('workspace')
        self.assertEqual(result.returncode, 0, result.stderr)
        exported = self.exported()
        self.assertEqual(Path(exported['ZSTANDARD_NATIVE_DART_PATH']), self.native)
        self.assertEqual(Path(exported['ZSTANDARD_NATIVE_PACKAGE_PATH']), self.root)
        self.assertEqual((self.native / 'lib/codec.dart').read_text(), 'const candidateCodec = true;\n')
        self.assertEqual(list(self.state.iterdir()), [])

    def test_private_cache_and_swift_root_contain_only_tracked_candidate_files(self):
        result = self.run_source()
        self.assertEqual(result.returncode, 0, result.stderr)
        exported = self.exported()
        cached = Path(exported['ZSTANDARD_NATIVE_DART_PATH'])
        swift_root = Path(exported['ZSTANDARD_NATIVE_PACKAGE_PATH'])
        self.assertTrue(cached.is_relative_to(self.state))
        self.assertEqual(cached.parts[-3:], ('hosted', 'pub.dev', 'zstandard_native-1.5.0'))
        self.assertEqual((cached / 'lib/codec.dart').read_bytes(), (swift_root / 'zstandard_native/lib/codec.dart').read_bytes())
        self.assertTrue((swift_root / 'Package.swift').is_file())
        self.assertFalse((cached / 'untracked-sentinel').exists())
        self.assertFalse((swift_root / 'zstandard_native/untracked-sentinel').exists())
        self.assertFalse(self.native.exists(), 'cache case must not fall back to workspace native sources')
        hidden = list(self.state.glob('*/workspace-native/untracked-sentinel'))
        self.assertEqual(len(hidden), 1)
        self.assertEqual(hidden[0].read_text(), 'private-untracked-value')

    def test_invalid_source_is_rejected_before_any_mutation(self):
        for source in ('published', '../outside', '', 'pub-cache\nINJECTED=true'):
            with self.subTest(source=source):
                result = self.run_source(source)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('invalid-source', result.stderr)
                self.assertTrue(self.native.is_dir())
                self.assertEqual(self.environment_file.read_text(), '')
                self.assertEqual(list(self.state.iterdir()), [])

    def test_ci_output_is_required_before_sources_are_moved(self):
        result = self.run_source(include_environment_file=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing-ci-environment', result.stderr)
        self.assertTrue(self.native.is_dir())
        self.assertEqual(list(self.state.iterdir()), [])

    def test_malformed_or_ambiguous_versions_are_rejected(self):
        for version in ('../escape', '1.5.0/escape', 'true', '1.5', '1.5.0\nversion: 2.0.0'):
            with self.subTest(version=version):
                (self.native / 'pubspec.yaml').write_text('name: zstandard_native\nversion: '+version+'\n')
                self.git('add', 'zstandard_native/pubspec.yaml')
                result = self.run_source()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('invalid-candidate-version', result.stderr)
                self.assertTrue(self.native.is_dir())
                self.assertEqual(list(self.state.iterdir()), [])

    def test_tracked_source_drift_is_rejected_without_hiding_the_workspace(self):
        (self.native / 'lib/codec.dart').write_text('uncommitted edit\n')
        result = self.run_source()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('native-source-drift', result.stderr)
        self.assertEqual((self.native / 'lib/codec.dart').read_text(), 'uncommitted edit\n')
        self.assertEqual(self.environment_file.read_text(), '')

    def test_tracked_links_cannot_copy_a_file_outside_the_repository(self):
        outside = self.parent / 'outside'
        outside.write_text('must-stay-private')
        try:
            (self.native / 'lib/external.dart').symlink_to(outside)
        except OSError as error:
            self.skipTest(f'local symlink support unavailable: {error.errno}')
        self.git('add', 'zstandard_native/lib/external.dart')
        result = self.run_source()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unsafe-candidate-path', result.stderr)
        self.assertTrue(self.native.is_dir())
        self.assertEqual(outside.read_text(), 'must-stay-private')
        self.assertEqual(list(self.state.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
