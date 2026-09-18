#!/usr/bin/env bash
set -euo pipefail

# guard-test-hygiene
# ------------------
# PreToolUse hook on Bash. WARNS (tier 1; does not block) when a test run is
# likely to stick in the foreground and stream large output into context —
# the "background tests block memory for no reason" failure. Steers long /
# slow / 2>&1-captured runs to the tracked, logged path:
#   uv run poe run_bg <task>   → detaches, writes to .pytest_logs/, tail it.
#
# It is the complement to guard-memory-hazards.sh (which BLOCKS 46 MB loads and
# unbounded benchmark runs). This one only nudges on test-run hygiene.
#
# Flip to blocking with TEST_HYGIENE_MODE=block; silence with TEST_HYGIENE_OFF=1.

if [[ "${TEST_HYGIENE_OFF:-0}" == "1" ]]; then exit 0; fi

_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

HOOK_STDIN_FILE="$_tmpf" python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
import re
import sys

MODE = os.environ.get("TEST_HYGIENE_MODE", "warn")

try:
    with open(os.environ["HOOK_STDIN_FILE"], encoding="utf-8") as fh:
        payload = json.load(fh)
except Exception:
    sys.exit(0)  # never break the tool call on a parse error

cmd = (payload.get("tool_input") or {}).get("command", "")
if not cmd:
    sys.exit(0)

# Only consider test-runner invocations.
is_test = bool(re.search(r"\b(pytest|vitest|npm (run )?test|poe (test|web_e2e|coverage)|cargo test)\b", cmd))
if not is_test:
    sys.exit(0)

# Already on the tracked/backgrounded path → fine.
backgrounded = bool(re.search(r"\b(run_bg|nohup)\b", cmd)) or re.search(r"&\s*disown", cmd) or re.search(r">\s*\S*\.pytest_logs", cmd)
if backgrounded:
    sys.exit(0)

reasons: list[str] = []

# 1) The known-slow / full-history / whole-suite foreground runs that hang.
if re.search(r"test_audit_results_roundtrip|--full-history|-m\s+slow|\bslow\b", cmd):
    reasons.append("targets the SLOW / full-history suite (loads large results.json) in the foreground")
# A bare whole-directory pytest with no node-id / -k / -q selection tends to be long.
if re.search(r"\bpytest\b", cmd) and not re.search(r"::|-k\b|-m\b|-q\b|--co\b|tests/\S+\.py", cmd):
    reasons.append("runs an unscoped pytest over the whole tree (long; scope with a node-id, -k, or -q)")

# 2) `2>&1` capture of a test run → streams the full (possibly huge) output into context.
if re.search(r"2>&1", cmd) and not re.search(r"\|\s*(tail|head)\b|>\s*[^&\s]", cmd):
    reasons.append("captures test output with 2>&1 into context (use a log file: `… > .pytest_logs/run.log 2>&1` then tail)")

if not reasons:
    sys.exit(0)

msg = (
    "test-hygiene: this test run may stick in the foreground and block memory.\n"
    + "".join(f"  • {r}\n" for r in reasons)
    + "  Prefer the tracked/logged path: `uv run poe run_bg <task>` (detaches → "
    ".pytest_logs/; tail the log). For a slice, scope with a node-id / -k / -q. "
    "Never `2>&1`-stream a big suite into context. (TEST_HYGIENE_OFF=1 to silence.)"
)

if MODE == "block":
    print(msg, file=sys.stderr)
    sys.exit(2)
# tier-1 warn: surface, do not block.
print(msg, file=sys.stderr)
sys.exit(0)
PYEOF
