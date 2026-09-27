#!/usr/bin/env bash
set -euo pipefail

# Capture stdin before the heredoc consumes it.
_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

# The detection logic (regex + scope) lives in one place —
# .claude/hooks/lib/match_dispatch_check.py — imported here and by the
# git pre-commit entry point (.claude/hooks/warn-match-dispatch.sh). See that
# module's docstring for why: CLAUDE.md's own documented Bash-heredoc
# write-gate workaround silently bypasses this PreToolUse hook, so the rule
# needs a second, non-bypassable enforcement point that shares — not
# duplicates — the check. GOV-07.
_hooks_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Quoted heredoc (<<'PYEOF') keeps the Python body literal; the temp stdin
# path and the lib dir are handed in via env vars.
HOOK_STDIN_FILE="$_tmpf" HOOK_LIB_DIR="$_hooks_dir/lib" python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.environ["HOOK_LIB_DIR"])
from match_dispatch_check import check_text  # noqa: E402


def allow() -> None:
    # Silent exit 0 = proceed; no stdout avoids hook-output schema validation.
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

tool_name = payload.get("tool_name", "") if isinstance(payload, dict) else ""
tool_input = payload.get("tool_input", {}) if isinstance(payload, dict) else {}
path_value = (tool_input.get("file_path") or tool_input.get("path")) if isinstance(tool_input, dict) else None
if not isinstance(path_value, str):
    allow()
    raise SystemExit(0)


def proposed_text() -> str | None:
    """Content that will exist after the call — PreToolUse runs before the
    write, so scan the proposed change, not the stale on-disk file."""
    from pathlib import Path

    path = Path(path_value)
    content = tool_input.get("content")
    new_string = tool_input.get("new_string")
    if tool_name == "Write" and isinstance(content, str):
        return content
    if tool_name == "Edit" and isinstance(new_string, str):
        old_string = tool_input.get("old_string") or ""
        if path.exists():
            try:
                disk = path.read_text(encoding="utf-8")
            except OSError:
                return new_string
            return disk.replace(old_string, new_string) if old_string and old_string in disk else new_string
        return new_string
    return path.read_text(encoding="utf-8") if path.exists() else None


text = proposed_text()
if text is None:
    allow()
    raise SystemExit(0)

reason = check_text(path_value, text)
if reason is not None:
    # Exit 2 blocks the tool call; stderr is surfaced back to Claude.
    print(reason, file=sys.stderr)
    raise SystemExit(2)

allow()
PYEOF
