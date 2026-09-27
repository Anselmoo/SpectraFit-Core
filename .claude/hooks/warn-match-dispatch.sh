#!/usr/bin/env bash
# [GIT PRE-COMMIT · WARN-ONLY FOR NOW — see NOT YET BLOCKING below]
#
# GOV-07: enforce-match-dispatch.sh (the Claude Code PreToolUse hook) is the
# most-cited "mechanically enforced" convention in CLAUDE.md — but it is
# registered ONLY as an Edit/Write PreToolUse matcher in .claude/settings.json,
# with no git-hook or CI equivalent. CLAUDE.md's own documented workaround for
# the self-assess write-gate ("use Bash heredoc/sed/python3 instead of
# Edit/Write") silently escapes it: a Bash-heredoc-written if/elif chain never
# passes through the PreToolUse matcher at all. This pre-commit gate closes
# that escape hatch for staged files, at the point a Bash-heredoc edit can no
# longer avoid detection.
#
# Shares detection logic with enforce-match-dispatch.sh via the single source
# of truth .claude/hooks/lib/match_dispatch_check.py — do not re-implement the
# regex/scope here; import the module, the way this script does.
#
# NOT YET BLOCKING. A 2026-08-21 sweep of the live tree found 5 pre-existing
# violations (python/oracles/inference.py, python/oracles/audit/claims.py,
# python/oracles/audit/provenance.py, tests/audit/test_claim_evidence_integrity.py,
# tests/unit/oracles/test_wave_a_tied_grid.py). Flipping this hook to blocking
# before those are fixed would fail every commit that merely touches an
# unrelated line in one of those files. Fix the 5 first (convert each to
# match/case), THEN change this hook's exit code below from 0 to 1 and drop
# `verbose: true` from its .pre-commit-config.yaml entry — mirrors how
# warn-grey-comments.sh documents its own "why this only warns".
set -uo pipefail

_hooks_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HOOK_LIB_DIR="$_hooks_dir/lib"

mapfile -t FILES < <(git diff --cached --name-only --diff-filter=ACM -- '*.py' 2>/dev/null)
[ ${#FILES[@]} -eq 0 ] && exit 0

FLAGGED_OUTPUT="$(HOOK_LIB_DIR="$HOOK_LIB_DIR" FILES_TO_CHECK="${FILES[*]}" python3 - <<'PYEOF'
import os
import sys

sys.path.insert(0, os.environ["HOOK_LIB_DIR"])
from match_dispatch_check import check_text

files = os.environ["FILES_TO_CHECK"].split()
found = []
for f in files:
    if not os.path.isfile(f):
        continue
    try:
        with open(f, encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    except OSError:
        continue
    reason = check_text(f, text)
    if reason:
        found.append(reason)

for reason in found:
    print(reason)
PYEOF
)"

if [ -n "$FLAGGED_OUTPUT" ]; then
    printf '\n\033[33m! match/case dispatch\033[0m — staged file(s) use an if/elif==... chain on a single\n'
    printf '  discriminator where CLAUDE.md Code Conventions calls for match/case:\n\n'
    echo "$FLAGGED_OUTPUT" | sed 's/^/    /'
    printf '\n  (warn-only for now — see this script'"'"'s header for why and what flips it to blocking)\n\n'
fi

exit 0
