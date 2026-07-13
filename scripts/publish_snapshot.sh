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

git remote add gitlab "$CI_REPOSITORY_URL" 2>/dev/null || true
git remote add github "https://x-access-token:${GITHUB_TOKEN}@github.com/Anselmoo/spectrafit-core.git" 2>/dev/null || true

uvx --from 'repo-release-tools==1.11.2' rrt git publish-snapshot github \
  --yes-i-know-this-overwrites-remote-history

echo "Purging stale GitHub Actions run history from the previous snapshot..."
python3 "$SCRIPT_DIR/purge_github_actions_runs.py" --repo Anselmoo/spectrafit-core --token "$GITHUB_TOKEN" \
  || echo "WARNING: Actions-run purge failed (see above) — publish itself succeeded; check GITHUB_TOKEN's Actions:Read-and-write scope."
