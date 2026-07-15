#!/usr/bin/env bash
# Shared GitHub sneak-preview publish sequence.
#
# Extracted from the formerly-inline `script:` block in publish:github
# (.gitlab/70-publish.yml) so publish:github and publish:github:fast call the
# exact same sequence and cannot drift apart. See that file's header comment
# for the full rationale behind each safety measure below (dependencies: [],
# rrt pinning, git identity, manual exclusion removal).
#
# Both `git remote add` calls below are idempotent (`|| true`) because
# publish:github:fast already adds the `github` remote itself (to read its
# current SHA for the diff-gate) before calling this script.
#
# Requires: $GITHUB_TOKEN (masked/protected CI variable) and
# $CI_REPOSITORY_URL (GitLab-provided) in the environment. Run from the repo
# root, on a checkout of `main`.
#
# CWE-522 hardening: GITHUB_TOKEN is never embedded in the `github` remote
# URL (that would persist it in plaintext in this checkout's `.git/config`,
# re-exposed by any later `git remote -v`/debug step or cache/artifact
# upload). Instead it's injected as an `http.extraheader` via the
# GIT_CONFIG_COUNT/KEY/VALUE environment mechanism (git >=2.31) — scoped to
# `https://github.com/` requests only, applied transparently to every child
# git invocation for the lifetime of this process (including the ones `rrt`
# issues internally), and never written to any file.
set -euo pipefail

echo "Smoke-testing GITHUB_TOKEN before any destructive action..."
HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${GITHUB_TOKEN}" -H "Accept: application/vnd.github+json" https://api.github.com/repos/Anselmoo/spectrafit-core)
if [ "$HTTP_CODE" != "200" ]; then
  echo "GITHUB_TOKEN smoke test failed (HTTP $HTTP_CODE) — aborting before touching git remotes."
  exit 1
fi
echo "Smoke test OK (HTTP 200)."

git config user.email "ci@spectrafit-core.invalid"
git config user.name "spectrafit-core CI"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/publish_remove_excluded.py"

AUTH_HEADER="Authorization: Basic $(printf '%s' "x-access-token:${GITHUB_TOKEN}" | base64 | tr -d '\n')"
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0="http.https://github.com/.extraheader"
export GIT_CONFIG_VALUE_0="$AUTH_HEADER"

git remote add gitlab "$CI_REPOSITORY_URL" 2>/dev/null || true
git remote add github "https://github.com/Anselmoo/spectrafit-core.git" 2>/dev/null || true

uvx --from 'repo-release-tools==1.11.2' rrt git publish-snapshot github \
  --yes-i-know-this-overwrites-remote-history

echo "Purging stale GitHub Actions run history from the previous snapshot..."
GITHUB_TOKEN="$GITHUB_TOKEN" python3 "$SCRIPT_DIR/purge_github_actions_runs.py" --repo Anselmoo/spectrafit-core \
  || echo "WARNING: Actions-run purge failed (see above) — publish itself succeeded; check GITHUB_TOKEN's Actions:Read-and-write scope."
