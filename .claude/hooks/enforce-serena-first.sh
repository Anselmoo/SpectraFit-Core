#!/usr/bin/env bash
set -euo pipefail

# enforce-serena-first
# --------------------
# PreToolUse hook on Grep. Warns (does not block in tier 1) when the
# search pattern looks like a code symbol — `fn foo`, `struct Bar`,
# `impl Trait`, `class Baz`, `def fit`. For these patterns, serena
# (find_symbol / find_referencing_symbols / get_symbols_overview) is
# significantly faster and more precise than a fresh grep.
#
# Tier 2 will flip to blocking (exit 2) once the consolidated stream
# skills are in place and the conductor enforces the contract.

_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

HOOK_STDIN_FILE="$_tmpf" python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
import re
import sys

# Mode: "warn" (tier 1) or "block" (tier 2+). Read from env so the
# project can flip without editing this file.
MODE = os.environ.get("SERENA_FIRST_MODE", "warn")

# Patterns that look like symbol-targeted greps. The presence of a
# language keyword next to an identifier is the signal — bare keywords
# (e.g. searching for the literal word "fn" in docs) are not.
_SYMBOL_PATTERNS = [
    re.compile(r"^\s*(\\?b)?fn\s+\w"),
    re.compile(r"^\s*(\\?b)?struct\s+\w"),
    re.compile(r"^\s*(\\?b)?impl\s+\w"),
    re.compile(r"^\s*(\\?b)?trait\s+\w"),
    re.compile(r"^\s*(\\?b)?enum\s+\w"),
    re.compile(r"^\s*(\\?b)?pub\s+(fn|struct|enum|trait|mod)\s+\w"),
    re.compile(r"^\s*class\s+\w"),
    re.compile(r"^\s*def\s+\w"),
    re.compile(r"^\s*async\s+def\s+\w"),
]


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

looks_like_symbol = any(rx.search(pattern) for rx in _SYMBOL_PATTERNS)
if not looks_like_symbol:
    allow()
    raise SystemExit(0)

msg = (
    f"[serena-first] Grep pattern {pattern!r} looks like a symbol search. "
    "Prefer mcp__serena__find_symbol / find_referencing_symbols / "
    "get_symbols_overview — serena indexes the project's symbol table "
    "and is faster + more precise than a cold grep. "
    "See CLAUDE.md § 'Tooling: use MCP servers for discovery'."
)

if MODE == "block":
    print(msg, file=sys.stderr)
    raise SystemExit(2)

# warn mode (default in tier 1): stderr only, don't block.
print(msg, file=sys.stderr)
raise SystemExit(0)
PYEOF
