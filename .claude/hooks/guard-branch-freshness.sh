#!/usr/bin/env bash
# guard-branch-freshness.sh — PreToolUse(Bash) hook.
#
# Reads the Claude hook JSON payload from stdin. If the Bash command matches
# a push/PR-creation pattern (git push, glab mr create, gh pr create),
# sources the git-hygiene lib and runs check_branch_freshness as a warn-only
# reminder to pull/rebase before creating a PR or pushing.
#
# All other commands → exit 0 immediately.
# GIT_HYGIENE_OFF=1 → no-op.
#
# Mirror of guard-test-hygiene.sh: parse cmd from stdin JSON, check, warn.
set -uo pipefail

if [[ "${GIT_HYGIENE_OFF:-0}" == "1" ]]; then exit 0; fi

# Read stdin into a temp file (same pattern as guard-test-hygiene.sh)
_tmpf="$(mktemp)"
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

HOOK_STDIN_FILE="$_tmpf" python3 - <<'PYEOF'
from __future__ import annotations
import json
import os
import re
import sys

try:
    with open(os.environ["HOOK_STDIN_FILE"], encoding="utf-8") as fh:
        payload = json.load(fh)
except Exception:
    sys.exit(0)  # never break on parse error

cmd = (payload.get("tool_input") or {}).get("command", "")
if not cmd:
    sys.exit(0)

# Only fire on push / PR-creation commands
is_push_or_pr = bool(re.search(
    r"\bgit\s+push\b|\bglab\s+mr\s+create\b|\bgh\s+pr\s+create\b",
    cmd,
))
if not is_push_or_pr:
    sys.exit(0)

# Signal the outer shell to run the freshness check
sys.exit(42)
PYEOF

py_rc=$?
if [[ "$py_rc" -eq 42 ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    # shellcheck source=lib/git-hygiene.sh
    source "$SCRIPT_DIR/lib/git-hygiene.sh"
    check_branch_freshness
fi

exit 0
