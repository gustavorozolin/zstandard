"""Use real Dart token listing to verify private CI configuration without uploads."""

import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[3]
DART = shutil.which('dart')
if DART:
    embedded = Path(DART).resolve().parent / 'cache/dart-sdk/bin/dart'
    if embedded.is_file():
        DART = str(embedded)


@unittest.skipUnless(DART and os.name == 'posix', 'Unix Dart SDK is required')
class FlutterProfileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='zstd-sdk-profile-')
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name).resolve()
        self.operator = self.root / 'operator home'
        self.operator.mkdir()
        sdk = self.root / 'sdk with spaces'
        (sdk / 'bin').mkdir(parents=True)
        (sdk / 'bin/dart').write_text('#!/bin/bash\nexec ' + shlex.quote(DART) + ' "$@"\n')
        (sdk / 'bin/dart').chmod(0o700)
        self.environment = {'PATH': os.environ['PATH'], 'HOME': str(self.operator),
                            'XDG_CONFIG_HOME': str(self.operator / '.config'),
                            'PUB_CACHE': str(self.root / 'shared package cache'),
                            'FLUTTER_ROOT': str(sdk), 'RUNNER_TEMP': str(self.root),
                            'GITHUB_ENV': str(self.root / 'github-env'),
                            'GITHUB_PATH': str(self.root / 'github-path')}
        for name in ['GITHUB_ENV', 'GITHUB_PATH']:
            Path(self.environment[name]).touch()
        self.original_store = self.token_file(self.operator, self.environment['XDG_CONFIG_HOME'])
        self.write_reference(self.original_store, 'https://operator-fixture.invalid')
        self.original_bytes = self.original_store.read_bytes()
        self.assertIn('operator-fixture.invalid', self.list_tokens(DART, self.environment))

    @staticmethod
    def token_file(home, config):
        base = home / 'Library/Application Support' if platform.system() == 'Darwin' else Path(config)
        return base / 'dart/pub-tokens.json'

    @staticmethod
    def write_reference(path, url):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'version': 1, 'hosted': [{'url': url, 'env': 'MISSING_FIXTURE_TOKEN'}]}))

    @staticmethod
    def list_tokens(executable, environment):
        result = subprocess.run([executable, 'pub', 'token', 'list'], env=environment,
                                capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return result.stdout

    def prepare(self):
        source = (ROOT / '.github/actions/setup-flutter/action.yml').read_text()
        self.assertEqual(source.count('      run: |\n'), 1)
        script = textwrap.dedent(source.split('      run: |\n', 1)[1])
        subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', script],
                       env=self.environment, check=True, timeout=15)
        environment = dict(self.environment)
        environment.update(dict(line.split('=', 1) for line in Path(environment['GITHUB_ENV']).read_text().splitlines()))
        wrapper = Path(Path(environment['GITHUB_PATH']).read_text().strip()) / 'dart'
        return wrapper, environment

    def test_dart_wrapper_uses_a_private_profile_and_preserves_the_shared_archive_cache(self):
        wrapper, environment = self.prepare()
        self.assertNotIn('operator-fixture.invalid', self.list_tokens(str(wrapper), environment))
        private_home = Path(environment['ZSTANDARD_FLUTTER_SETTINGS_HOME'])
        self.write_reference(self.token_file(private_home, environment['XDG_CONFIG_HOME']),
                             'https://private-fixture.invalid')
        self.assertIn('private-fixture.invalid', self.list_tokens(str(wrapper), environment))
        self.assertEqual(environment['PUB_CACHE'], self.environment['PUB_CACHE'])
        self.assertEqual(self.original_store.read_bytes(), self.original_bytes)

    @unittest.skipUnless(platform.system() == 'Linux', 'The publisher uses Linux XDG configuration')
    def test_direct_sdk_invocation_uses_the_same_private_token_store(self):
        wrapper, environment = self.prepare()
        private_home = Path(environment['ZSTANDARD_FLUTTER_SETTINGS_HOME'])
        self.write_reference(self.token_file(private_home, environment['XDG_CONFIG_HOME']),
                             'https://private-fixture.invalid')
        direct = self.list_tokens(DART, environment)
        self.assertIn('private-fixture.invalid', direct)
        self.assertNotIn('operator-fixture.invalid', direct)
        self.assertEqual(self.original_store.read_bytes(), self.original_bytes)


if __name__ == '__main__':
    unittest.main()
