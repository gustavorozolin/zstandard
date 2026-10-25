#!/usr/bin/env python3
"""Record candidate evidence and verify it before any package publication.

Copilot owns deployment state. This adapter only reads its promotion receipt
and the successful preparation run; it never creates branches, tags or releases.
"""

import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote
import zipfile


WORKFLOW = '.github/workflows/release_workflow.yml'
VERSION = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')
SHA = re.compile(r'[a-f0-9]{40}')
MARKER = re.compile(
    r'<!-- copilot-deployment operation-id="([A-Za-z0-9][A-Za-z0-9._-]{7,127})" '
    r'phase="promotion" issue="([1-9][0-9]*)" -->'
)


class InvalidCandidate(Exception):
    pass


def require(condition, message):
    if not condition:
        raise InvalidCandidate(message)


def git(*args):
    result = subprocess.run(['git', *args], text=True, capture_output=True)
    require(result.returncode == 0, 'Candidate Git verification failed.')
    return result.stdout.strip()


def release_branch(version):
    branch = f'{os.environ.get("RELEASE_TREE") or "release"}/{version}'
    git('check-ref-format', f'refs/heads/{branch}')
    return branch


def repository():
    value = os.environ.get('GITHUB_REPOSITORY', '')
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value),
            'A valid GitHub repository is required.')
    return value


class GitHub:
    def __init__(self, repo):
        self.repo = repo

    def read(self, endpoint, *, binary=False):
        result = subprocess.run(
            ['gh', 'api', f'repos/{self.repo}/{endpoint}'], capture_output=True)
        require(result.returncode == 0, 'Unable to read GitHub release evidence.')
        return result.stdout if binary else json.loads(result.stdout)


def operation_for_promotion(pull, issue, repo, version, source, production):
    matches = MARKER.findall(pull.get('body') or '')
    require(len(matches) == 1, 'A unique Copilot promotion marker is required.')
    operation_id, issue_text = matches[0]
    require(issue.get('number') == int(issue_text) and not issue.get('pull_request'),
            'The promotion launcher must be the recorded issue.')
    body = issue.get('body') or ''
    start = '<!-- copilot-configuration-start'
    end = 'copilot-configuration-end -->'
    require(body.count(start) == 1 and body.count(end) == 1,
            'The launcher must contain one durable Copilot configuration.')
    payload = json.loads(body.split(start, 1)[1].split(end, 1)[0])
    state = payload.get('deploymentOrchestration') or {}
    failure = state.get('lastFailure') or {}
    phase = (failure.get('previousPhase') if state.get('phase') == 'blocked'
             and failure.get('retryable') is True else state.get('phase'))
    require(payload.get('schemaVersion') == 3
            and state.get('stateVersion') == 1
            and type(state.get('revision')) is int and state['revision'] > 0,
            'The launcher has no supported durable deployment state.')
    require(state.get('kind') == 'release'
            and state.get('operationId') == operation_id
            and state.get('version') == version
            and state.get('tag') == f'v{version}'
            and state.get('sourceBranch') == release_branch(version)
            and state.get('sourceSha') == source
            and state.get('productionSha') == production
            and state.get('publicationWorkflow') == 'release_workflow.yml'
            and phase in ['publishing', 'published', 'reconciliation_pending', 'completed'],
            'The tag does not own the accepted Copilot release operation.')
    require(pull.get('merged_at') and pull.get('merge_commit_sha') == production
            and pull.get('number') == state.get('promotionPullRequest')
            and pull.get('head', {}).get('sha') == source
            and pull.get('head', {}).get('ref') == state['sourceBranch']
            and pull.get('head', {}).get('repo', {}).get('full_name') == repo
            and pull.get('base', {}).get('ref') == state.get('productionBranch')
            and pull.get('base', {}).get('repo', {}).get('full_name') == repo,
            'The accepted production commit must be the recorded promotion merge.')
    return int(issue_text), operation_id


def candidate_from_archive(content):
    require(len(content) <= 65536, 'Candidate evidence archive is too large.')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        require(len(entries) == 1 and entries[0].filename == 'release-candidate.json'
                and entries[0].file_size <= 16384,
                'Candidate evidence archive has unexpected contents.')
        return json.loads(archive.read(entries[0]))


def valid_preparation_run(run, repo, branch):
    return (run.get('status') == 'completed' and run.get('conclusion') == 'success'
            and run.get('event') == 'workflow_dispatch'
            and run.get('path') == WORKFLOW and run.get('head_branch') == branch
            and run.get('head_repository', {}).get('full_name') == repo)


def validate_receipt(receipt, run, repo, version, source, tree, issue):
    expected = dict(schemaVersion=1, repository=repo, version=version,
                    sourceSha=source, treeSha=tree, issue=issue,
                    runId=run['id'], runAttempt=run['run_attempt'])
    require(isinstance(receipt, dict) and receipt == expected
            and all(type(receipt[key]) is type(value) for key, value in expected.items()),
            'Preparation evidence does not match this candidate and workflow attempt.')


def record(version, issue_text, output):
    require(issue_text.isdecimal() and int(issue_text) > 0,
            'A positive launcher issue is required.')
    require(os.environ.get('GITHUB_REF_NAME') == release_branch(version),
            'Evidence can only be recorded on the matching release branch.')
    receipt = dict(schemaVersion=1, repository=repository(), version=version,
                   sourceSha=git('rev-parse', 'HEAD'), treeSha=git('rev-parse', 'HEAD^{tree}'),
                   issue=int(issue_text), runId=int(os.environ['GITHUB_RUN_ID']),
                   runAttempt=int(os.environ['GITHUB_RUN_ATTEMPT']))
    Path(output).write_text(json.dumps(receipt, sort_keys=True) + '\n')


def verify(version, source, production, api=None):
    require(SHA.fullmatch(source) and SHA.fullmatch(production), 'Full commit SHAs are required.')
    repo = repository()
    api = api or GitHub(repo)
    require(git('rev-parse', f'{source}^{{tree}}') == git('rev-parse', f'{production}^{{tree}}'),
            'Production content differs from the tested candidate; prepare a reconciled candidate.')
    pulls = api.read(f'commits/{production}/pulls?per_page=100')
    candidates = [pull for pull in pulls if pull.get('merge_commit_sha') == production
                  and pull.get('merged_at') and MARKER.search(pull.get('body') or '')]
    require(len(candidates) == 1, 'The tag needs exactly one accepted Copilot promotion.')
    pull = candidates[0]
    issue_text = MARKER.findall(pull.get('body') or '')[0][1]
    issue = api.read(f'issues/{issue_text}')
    launcher, operation_id = operation_for_promotion(pull, issue, repo, version, source, production)
    branch = release_branch(version)
    runs = api.read('actions/workflows/release_workflow.yml/runs'
                    f'?branch={quote(branch, safe="")}&event=workflow_dispatch&status=success&per_page=100')
    tree = git('rev-parse', f'{source}^{{tree}}')
    for run in runs.get('workflow_runs', []):
        if not valid_preparation_run(run, repo, branch):
            continue
        artifacts = api.read(f'actions/runs/{run["id"]}/artifacts?per_page=100')
        matches = [item for item in artifacts.get('artifacts', [])
                   if item.get('name') == f'release-candidate-{version}'
                   and item.get('expired') is False]
        if len(matches) != 1:
            continue
        receipt = candidate_from_archive(api.read(
            f'actions/artifacts/{matches[0]["id"]}/zip', binary=True))
        try:
            validate_receipt(receipt, run, repo, version, source, tree, launcher)
        except InvalidCandidate:
            continue
        git('merge-base', '--is-ancestor', run['head_sha'], source)
        return launcher, operation_id
    raise InvalidCandidate('No successful preparation run attests this exact candidate.')


def main(args):
    require(len(args) == 4 and args[0] in ['record', 'verify'],
            'Usage: release_candidate.py record VERSION ISSUE OUTPUT | verify VERSION SOURCE_SHA PRODUCTION_SHA')
    mode, version, first, second = args
    require(VERSION.fullmatch(version), 'A stable release version is required.')
    if mode == 'record':
        record(version, first, second)
    else:
        issue, operation_id = verify(version, first, second)
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write(f'issue={issue}\noperation-id={operation_id}\n')
        print('Verified successful candidate preparation and accepted Copilot promotion.')


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (InvalidCandidate, ValueError, KeyError, OSError, zipfile.BadZipFile) as error:
        print(f'Release candidate verification failed: {error}', file=sys.stderr)
        sys.exit(1)
