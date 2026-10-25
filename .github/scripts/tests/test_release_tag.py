"""Exercise tag classification against real local Git origins; no publication."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts/check_release_tag.sh'


class ReleaseTagTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='zstd-release-tag-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        # Real local Git fixtures must not inherit the operator's hooks or config.
        template = self.root / 'empty-template'
        template.mkdir()
        self.environment = {**os.environ, 'GIT_CONFIG_GLOBAL': os.devnull,
                            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TEMPLATE_DIR': str(template)}
        self.repository = self.root / 'repository'
        self.repository.mkdir()
        self.origin = self.root / 'origin.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(self.origin)], check=True, env=self.environment)
        self.git('init', '-q', '-b', 'master')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.commit('base')
        self.base = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('remote', 'add', 'origin', str(self.origin))
        self.git('push', '-q', 'origin', 'master')
        self.output = self.root / 'outputs'
        self.output.touch()

    def git(self, *args):
        result = subprocess.run(['git', *args], cwd=self.repository, env=self.environment, text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(f'Local fixture Git command failed: {args}: {result.stderr}')
        return result

    def commit(self, value):
        (self.repository / 'fixture').write_text(value)
        self.git('add', 'fixture')
        self.git('commit', '-qm', value)

    def candidate(self, prefix):
        branch = prefix + '/1.6.0'
        self.git('checkout', '-qb', branch)
        self.commit('candidate ' + prefix)
        self.git('push', '-q', 'origin', branch)
        return branch

    def classify(self, tag='v1.6.0', prefix='hotfix', production='master', release_prefix='release'):
        return subprocess.run(['bash', str(SCRIPT)], cwd=self.repository,
                              env={**self.environment, 'GITHUB_REF_NAME': tag,
                                   'GITHUB_OUTPUT': str(self.output),
                                   'GITHUB_STEP_SUMMARY': str(self.root / 'summary'),
                                   'HOTFIX_TREE': prefix, 'MAIN_BRANCH': production,
                                   'RELEASE_TREE': release_prefix},
                              capture_output=True, text=True, timeout=15)

    def test_accepted_release_production_merge_can_enter_publication_validation(self):
        branch = self.candidate('release')
        self.git('checkout', '-q', 'master')
        self.git('merge', '-q', '--no-ff', branch, '-m', 'accepted production')
        self.git('push', '-q', 'origin', 'master')
        self.git('tag', 'v1.6.0')
        result = self.classify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('kind=release\n', self.output.read_text())

    def test_release_tag_before_production_promotion_is_rejected(self):
        self.candidate('release')
        self.git('tag', 'v1.6.0')
        self.assertNotEqual(self.classify().returncode, 0)
        self.assertEqual(self.output.read_text(), '')

    def test_configured_production_and_release_prefix_accept_the_owned_merge(self):
        production = 'production/stable'
        self.git('checkout', '-qb', production)
        self.git('push', '-q', 'origin', production)
        branch = self.candidate('deployment/release')
        self.git('checkout', '-q', production)
        self.git('merge', '-q', '--no-ff', branch, '-m', 'accepted production')
        self.git('push', '-q', 'origin', production)
        self.git('tag', 'v1.6.0')
        result = self.classify(production=production, release_prefix='deployment/release')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('kind=release\n', self.output.read_text())

    def test_master_acceptance_cannot_replace_configured_production_acceptance(self):
        production = 'production/stable'
        self.git('push', '-q', 'origin', f'HEAD:{production}')
        branch = self.candidate('release')
        self.git('checkout', '-q', 'master')
        self.git('merge', '-q', '--no-ff', branch, '-m', 'only accepted on master')
        self.git('push', '-q', 'origin', 'master')
        self.git('tag', 'v1.6.0')
        self.assertNotEqual(self.classify(production=production).returncode, 0)
        self.assertEqual(self.output.read_text(), '')

    def test_configured_production_hotfix_preserves_nonpublication(self):
        production = 'production/stable'
        self.git('checkout', '-qb', production)
        branch = self.candidate('hotfix')
        self.git('checkout', '-q', production)
        self.git('merge', '-q', '--no-ff', branch, '-m', 'accepted hotfix')
        self.git('push', '-q', 'origin', production)
        self.git('tag', 'v1.6.0')
        result = self.classify(production=production)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('kind=hotfix\n', self.output.read_text())
        self.assertIn('does not publish hotfix packages', (self.root / 'summary').read_text())

    def test_accepted_default_and_custom_hotfixes_preserve_nonpublication(self):
        for prefix in ['hotfix', 'maintenance/hotfix']:
            with self.subTest(prefix=prefix):
                self.git('checkout', '-q', 'master')
                branch = self.candidate(prefix)
                self.git('checkout', '-q', 'master')
                self.git('merge', '-q', '--no-ff', branch, '-m', 'accepted production')
                self.git('push', '-q', 'origin', 'master')
                self.git('tag', '-f', 'v1.6.0')
                result = self.classify(prefix=prefix)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('kind=hotfix\n', self.output.read_text())
                self.assertIn('does not publish hotfix packages', (self.root / 'summary').read_text())
                self.output.write_text('')

    def test_tag_behind_prepared_release_is_rejected(self):
        self.candidate('release')
        self.git('tag', 'v1.6.0', self.base)
        self.git('checkout', '-q', 'v1.6.0')
        self.assertNotEqual(self.classify().returncode, 0)
        self.assertEqual(self.output.read_text(), '')

    def test_hotfix_not_accepted_in_production_is_rejected(self):
        self.candidate('hotfix')
        self.git('tag', 'v1.6.0')
        self.assertNotEqual(self.classify().returncode, 0)
        self.assertEqual(self.output.read_text(), '')

    def test_unclassified_and_malformed_tags_are_rejected(self):
        self.git('tag', 'v1.6.0')
        for tag in ['v1.6.0', 'v01.6.0', 'v1.6.0-rc.1', '1.6.0']:
            with self.subTest(tag=tag):
                self.assertNotEqual(self.classify(tag=tag).returncode, 0)
                self.assertEqual(self.output.read_text(), '')

    def test_checkout_must_equal_the_tag(self):
        self.candidate('release')
        self.git('tag', 'v1.6.0', self.base)
        self.assertNotEqual(self.classify().returncode, 0)
        self.assertEqual(self.output.read_text(), '')


if __name__ == '__main__':
    unittest.main()
