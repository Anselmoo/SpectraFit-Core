#!/usr/bin/env bash
set -euo pipefail

# PreToolUse — BLOCKING (exit 2).
# Guards tests/fixtures/nist_strd/**  against accidental edits.
#
# Context: NIST StRD (Statistical Reference Datasets) fixture files contain
# verbatim certified numerical data sourced from itl.nist.gov. Any
# "formatting improvement" or reformatting corrupts the V&V chain used to
# certify spectrafit's solver accuracy.
#
# Cycle 16 ADR (Eckerle4) and Cycle 16.C/D/E (Gauss2, Gauss3, Lanczos1)
# document why these files must only change via a controlled fresh fetch from
# the NIST server — never by hand-editing.
#
# The only fields allowed to change (and only via fresh NIST fetch) are:
#   _RAW, CERTIFIED, START1, START2, RSS, DOF, N_OBS
#
# Direct the user to the `nist-strd-runner` skill for any update workflow.

_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

HOOK_STDIN_FILE="$_tmpf" python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def allow() -> None:
    raise SystemExit(0)


with open(os.environ["HOOK_STDIN_FILE"], encoding="utf-8") as _fh:
    raw = _fh.read().strip()

if not raw:
    allow()

try:
    payload = json.loads(raw)
except json.JSONDecodeError:
    allow()

tool_input = payload.get("tool_input", {}) if isinstance(payload, dict) else {}
path_value = (tool_input.get("file_path") or tool_input.get("path")) if isinstance(tool_input, dict) else None
if not isinstance(path_value, str):
    allow()

path = Path(path_value)
normalized = path.as_posix()

# Match tests/fixtures/nist_strd/ (relative or absolute)
is_nist = (
    "tests/fixtures/nist_strd/" in normalized
    or normalized.startswith("tests/fixtures/nist_strd/")
)
if not is_nist:
    allow()

# It is a NIST fixture file — block the edit.
msg = (
    "[protect-nist-fixtures] BLOCKED: {path}\n"
    "\n"
    "  tests/fixtures/nist_strd/ contains *verbatim NIST StRD certified data*\n"
    "  (itl.nist.gov). Editing these files by hand corrupts the spectrafit V&V\n"
    "  chain (solver accuracy certification).\n"
    "\n"
    "  Only the following fields may change, and ONLY via a fresh fetch from\n"
    "  itl.nist.gov (never hand-edited):\n"
    "    _RAW, CERTIFIED, START1, START2, RSS, DOF, N_OBS\n"
    "\n"
    "  Relevant ADRs:\n"
    "    - Cycle 16 (Eckerle4): first NIST fixture hardening\n"
    "    - Cycle 16.C/D/E (Gauss2, Gauss3, Lanczos1): fixture chain extended\n"
    "\n"
    "  To update NIST data legitimately, use the `nist-strd-runner` skill\n"
    "  which fetches fresh data from itl.nist.gov and regenerates the fixtures\n"
    "  under a controlled diff review.\n"
    "\n"
    "  If you are CERTAIN this edit is a controlled NIST data refresh, confirm\n"
    "  explicitly in your next message and the hook will not re-block."
).format(path=normalized)

print(msg, file=sys.stderr)
raise SystemExit(2)
PYEOF
