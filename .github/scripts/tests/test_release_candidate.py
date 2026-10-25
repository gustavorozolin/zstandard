"""Verify publication admission with real Git commits and isolated API fixtures."""

import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('release_candidate', ROOT / 'scripts/release_candidate.py')
candidate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(candidate)


class FakeGitHub:
    def __init__(self, responses):
        self.responses = responses

    def read(self, endpoint, **options):
        return self.responses[endpoint]


class CandidateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='zstd-candidate-evidence-')
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        environment = {**os.environ, 'GIT_CONFIG_GLOBAL': os.devnull,
                       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TEMPLATE_DIR': str(self.root / 'template')}
        (self.root / 'template').mkdir()
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, environment).start()
        patch.dict(os.environ, GITHUB_REPOSITORY='fixture/zstandard').start()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.root / 'codec').write_text('candidate')
        self.git('add', 'codec')
        self.git('commit', '-qm', 'candidate')
        self.source = self.git('rev-parse', 'HEAD')
        self.tree = self.git('rev-parse', 'HEAD^{tree}')
        self.git('commit', '--allow-empty', '-qm', 'accepted production')
        self.production = self.git('rev-parse', 'HEAD')
        self.repo = 'fixture/zstandard'
        self.operation = dict(stateVersion=1, revision=2, kind='release',
                              operationId='operation-123', version='1.6.0', tag='v1.6.0',
                              sourceBranch='release/1.6.0', sourceSha=self.source,
                              productionSha=self.production, productionBranch='master',
                              publicationWorkflow='release_workflow.yml', phase='publishing',
                              promotionPullRequest=8)
        self.pull = dict(number=8, merged_at='2026-10-25T00:00:00Z',
                         merge_commit_sha=self.production,
                         body='<!-- copilot-deployment operation-id="operation-123" phase="promotion" issue="7" -->',
                         head=dict(sha=self.source, ref='release/1.6.0', repo=dict(full_name=self.repo)),
                         base=dict(ref='master', repo=dict(full_name=self.repo)))
        self.run = dict(id=42, run_attempt=1, status='completed', conclusion='success',
                        event='workflow_dispatch', path=candidate.WORKFLOW,
                        head_branch='release/1.6.0', head_repository=dict(full_name=self.repo),
                        head_sha=self.source)
        self.receipt = dict(schemaVersion=1, repository=self.repo, version='1.6.0',
                            sourceSha=self.source, treeSha=self.tree, issue=7,
                            runId=42, runAttempt=1)

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout.strip()

    def issue(self):
        return dict(number=7, body='<!-- copilot-configuration-start\n' + json.dumps(
            dict(schemaVersion=3, deploymentOrchestration=self.operation)) + '\ncopilot-configuration-end -->')

    def archive(self, name='release-candidate.json'):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as output:
            output.writestr(name, json.dumps(self.receipt))
        return stream.getvalue()

    def responses(self):
        return {
            f'commits/{self.production}/pulls?per_page=100': [self.pull],
            'issues/7': self.issue(),
            'actions/workflows/release_workflow.yml/runs?branch=release%2F1.6.0&event=workflow_dispatch&status=success&per_page=100': dict(workflow_runs=[self.run]),
            'actions/runs/42/artifacts?per_page=100': dict(artifacts=[dict(id=9, name='release-candidate-1.6.0', expired=False)]),
            'actions/artifacts/9/zip': self.archive(),
        }

    def verify(self, responses=None):
        with patch.object(candidate, 'git', side_effect=self.git):
            return candidate.verify('1.6.0', self.source, self.production,
                                    FakeGitHub(responses or self.responses()))

    def test_success_requires_both_successful_ci_and_the_owned_promotion(self):
        self.assertEqual(self.verify(), (7, 'operation-123'))

    def test_failed_skipped_fork_and_unrelated_workflow_runs_cannot_attest(self):
        original = copy.deepcopy(self.run)
        for change in [dict(conclusion='failure'), dict(conclusion='cancelled'),
                       dict(conclusion='skipped'), dict(status='in_progress'),
                       dict(path='.github/workflows/other.yml'),
                       dict(event='pull_request'), dict(head_branch='master'),
                       dict(head_repository=dict(full_name='fork/zstandard'))]:
            with self.subTest(change=change):
                self.run = {**original, **change}
                with self.assertRaises(candidate.InvalidCandidate):
                    self.verify()

    def test_wrong_commit_tree_issue_run_or_attempt_receipts_are_rejected(self):
        original = copy.deepcopy(self.receipt)
        for key, value in [('sourceSha', self.production), ('treeSha', 'a' * 40),
                           ('issue', 9), ('runId', 43), ('runAttempt', 2),
                           ('repository', 'fork/zstandard'), ('version', '1.6.1'),
                           ('runAttempt', True), ('schemaVersion', True)]:
            with self.subTest(key=key):
                self.receipt = {**original, key: value}
                with self.assertRaises(candidate.InvalidCandidate):
                    self.verify()

    def test_wrong_operation_or_production_and_unaccepted_phases_are_rejected(self):
        original = copy.deepcopy(self.operation)
        for change in [dict(operationId='other-operation'), dict(productionSha=self.source),
                       dict(sourceSha=self.production), dict(phase='promotion_pr_pending'),
                       dict(promotionPullRequest=9), dict(publicationWorkflow='hotfix_workflow.yml')]:
            with self.subTest(change=change):
                self.operation = {**original, **change}
                with self.assertRaises(candidate.InvalidCandidate):
                    self.verify()

    def test_retryable_failed_publication_can_reuse_the_same_immutable_evidence(self):
        self.operation.update(phase='blocked', lastFailure=dict(retryable=True, previousPhase='publishing'))
        self.assertEqual(self.verify(), (7, 'operation-123'))
        self.operation['lastFailure']['retryable'] = False
        with self.assertRaises(candidate.InvalidCandidate):
            self.verify()

    def test_production_content_drift_is_rejected_before_api_access(self):
        (self.root / 'codec').write_text('untested production content')
        self.git('add', 'codec')
        self.git('commit', '-qm', 'drift')
        production = self.git('rev-parse', 'HEAD')
        with patch.object(candidate, 'git', side_effect=self.git):
            with self.assertRaisesRegex(candidate.InvalidCandidate, 'differs'):
                candidate.verify('1.6.0', self.source, production, FakeGitHub({}))

    def test_missing_expired_and_ambiguous_evidence_fails_closed(self):
        for artifacts in [[], [dict(id=9, name='release-candidate-1.6.0', expired=True)],
                          [dict(id=n, name='release-candidate-1.6.0', expired=False) for n in [9, 10]]]:
            with self.subTest(artifacts=artifacts):
                responses = self.responses()
                responses['actions/runs/42/artifacts?per_page=100'] = dict(artifacts=artifacts)
                with self.assertRaises(candidate.InvalidCandidate):
                    self.verify(responses)

    def test_archive_paths_are_never_extracted_or_trusted(self):
        with self.assertRaises(candidate.InvalidCandidate):
            candidate.candidate_from_archive(self.archive('../release-candidate.json'))

    def test_record_reads_the_actual_candidate_and_attempt(self):
        output = self.root / 'record.json'
        with patch.dict(os.environ, GITHUB_REF_NAME='release/1.6.0', GITHUB_RUN_ID='42', GITHUB_RUN_ATTEMPT='1'):
            with patch.object(candidate, 'git', side_effect=self.git):
                candidate.record('1.6.0', '7', output)
        self.assertEqual(json.loads(output.read_text()), {**self.receipt, 'sourceSha': self.production})


if __name__ == '__main__':
    unittest.main()
