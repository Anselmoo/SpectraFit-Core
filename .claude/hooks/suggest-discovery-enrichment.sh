#!/usr/bin/env bash
set -euo pipefail

# suggest-discovery-enrichment
# -----------------------------
# PreToolUse hook on Grep. When the search pattern contains a bug/issue
# keyword (error, fail, wrong, incorrect, fixme, todo, bug, issue, panic,
# assert, traceback, exception, crash, broken, regression), reminds the
# agent to apply BPDD discovery-enrichment before acting — upstream issues,
# cross-repo instances, library API confirmation, broader context.
#
# This hook is always NON-BLOCKING (never exits 2). Its only effect is a
# stderr nudge. Set DISCOVERY_ENRICHMENT_MODE=off to silence completely.

_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

HOOK_STDIN_FILE="$_tmpf" python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
import re
import sys

# Mode: "warn" (default) or "off" (silent). Never blocks (no "block" tier).
MODE = os.environ.get("DISCOVERY_ENRICHMENT_MODE", "warn")

if MODE == "off":
    raise SystemExit(0)

# Bug/issue keywords (case-insensitive, whole-word or substring match).
_BUG_KEYWORDS = re.compile(
    r"(error|fail|wrong|incorrect|fixme|todo|bug|issue|panic|"
    r"assert|traceback|exception|crash|broken|regression)",
    re.IGNORECASE,
)


def allow() -> None:
    return


with open(os.environ["HOOK_STDIN_FILE"], encoding="utf-8") as _fh:
    raw = _fh.read().strip()

if not raw:
    allow()
    raise SystemExit(0)

try:
    payload = json.loads(raw)
except json.JSONDecodeError:
    allow()
    raise SystemExit(0)

if not isinstance(payload, dict):
    allow()
    raise SystemExit(0)

tool_name = payload.get("tool_name", "")
if tool_name != "Grep":
    allow()
    raise SystemExit(0)

tool_input = payload.get("tool_input", {})
pattern = tool_input.get("pattern", "") if isinstance(tool_input, dict) else ""
if not isinstance(pattern, str) or not pattern:
    allow()
    raise SystemExit(0)

if not _BUG_KEYWORDS.search(pattern):
    allow()
    raise SystemExit(0)

msg = (
    f"[bpdd-enrichment] Bug/issue grep {pattern!r}. BPDD-MAP enrichment:\n"
    "  • mcp__github__search_issues   — upstream reports of this class\n"
    "  • mcp__github__search_code     — cross-repo instances\n"
    "  • mcp__github__get_file_contents — upstream implementation comparison\n"
    "  • context7 (npx ctx7@latest)   — confirm library API before ENFORCE\n"
    "  • WebSearch / WebFetch          — broader context + error messages\n"
    "See BPDD § 'Discovery enrichment'. DISCOVERY_ENRICHMENT_MODE=off to silence."
)

# Always warn, never block.
print(msg, file=sys.stderr)
raise SystemExit(0)
PYEOF
