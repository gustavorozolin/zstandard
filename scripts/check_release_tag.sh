#!/usr/bin/env bash
# Read-only classification; package publication requires accepted production.
set -euo pipefail
tag="${GITHUB_REF_NAME:?Missing tag context}"
version="${tag#v}"
if [[ "$tag" != v* || ! "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
  echo 'Expected a stable vMAJOR.MINOR.PATCH tag.' >&2
  exit 1
fi
commit="$(git rev-parse --verify HEAD)"
tag_commit="$(git rev-parse --verify "refs/tags/$tag^{commit}")"
[[ "$commit" == "$tag_commit" ]] || { echo 'Checkout differs from the immutable tag.' >&2; exit 1; }
release="release/$version"
if git ls-remote --exit-code --heads origin "refs/heads/$release" >/dev/null; then
  git fetch --no-tags origin "refs/heads/$release:refs/remotes/origin/$release"
  source_commit="$(git rev-parse "refs/remotes/origin/$release")"
  git fetch --no-tags origin 'refs/heads/master:refs/remotes/origin/master'
  git merge-base --is-ancestor "$source_commit" "$commit" &&
    git merge-base --is-ancestor "$commit" refs/remotes/origin/master || {
    echo 'Release tag is not an accepted production descendant of its candidate.' >&2; exit 1;
  }
  kind=release
else
  hotfix="${HOTFIX_TREE:-hotfix}/$version"
  git check-ref-format "refs/heads/$hotfix"
  git ls-remote --exit-code --heads origin "refs/heads/$hotfix" >/dev/null || {
    echo 'No matching prepared release or hotfix branch exists.' >&2; exit 1;
  }
  git fetch --no-tags origin \
    "refs/heads/$hotfix:refs/remotes/origin/$hotfix" \
    'refs/heads/master:refs/remotes/origin/master'
  git merge-base --is-ancestor "refs/remotes/origin/$hotfix" "$commit" &&
    git merge-base --is-ancestor "$commit" refs/remotes/origin/master || {
      echo 'Hotfix tag is not an accepted production descendant of its candidate.' >&2; exit 1;
    }
  # Preserve the existing Copilot hotfix contract: GitHub release only.
  kind=hotfix
  source_commit="$(git rev-parse "refs/remotes/origin/$hotfix")"
fi
{
  printf 'version=%s\n' "$version"
  printf 'commit=%s\n' "$commit"
  printf 'kind=%s\n' "$kind"
  printf 'source-commit=%s\n' "$source_commit"
} >> "${GITHUB_OUTPUT:?Missing output context}"
printf 'Verified %s tag: %s\n' "$kind" "$tag"
if [[ "$kind" == hotfix && -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  printf '%s\n' 'Accepted Copilot hotfix tag. Its GitHub release is managed by Copilot; this workflow does not publish hotfix packages to pub.dev.' >> "$GITHUB_STEP_SUMMARY"
fi
