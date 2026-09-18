#!/usr/bin/env bash
set -euo pipefail

# Capture stdin before the heredoc consumes it.
_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

# Quoted heredoc (<<'PYEOF') keeps the Python body literal; the temp path is
# handed in via the HOOK_STDIN_FILE env var (mirrors enforce-match-dispatch.sh).
HOOK_STDIN_FILE="$_tmpf" python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


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

path = Path(path_value)
normalized = path.as_posix()
# Benchmark engine trees — their specs/outcomes/records must be Pydantic models.
# Covers the canonical python/oracles/ engine tree (benchmark/ was folded in, F13).
# parallel tree, so the @dataclass/NamedTuple ban applies to both (the canonical
# tree was previously uncovered by any pydantic hook).
_TARGET_PREFIXES = ("python/oracles/",)
is_target = normalized.startswith(_TARGET_PREFIXES) and path.suffix == ".py"
if not is_target:
    allow()
    raise SystemExit(0)


def proposed_text() -> str | None:
    """Content that will exist after the call — PreToolUse runs before the
    write, so scan the proposed change, not the stale on-disk file."""
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

# For Edit, scan only the introduced text so we don't block on context the user
# is merely moving; for Write the whole content is "introduced".
new_string = tool_input.get("new_string")
scan = new_string if (tool_name == "Edit" and isinstance(new_string, str)) else text

violations: list[str] = []

# @dataclass (with or without args) — require Pydantic BaseModel instead.
if re.search(r"^[ \t]*@dataclass\b", scan, re.MULTILINE) or re.search(r"\bdataclasses\.dataclass\b", scan):
    violations.append("@dataclass is banned in python/oracles/ — use a Pydantic BaseModel.")

# typing.NamedTuple — class form (class X(NamedTuple):) or functional form.
if re.search(r"\bNamedTuple\b", scan):
    violations.append("NamedTuple is banned in python/oracles/ — use a Pydantic BaseModel.")

if violations:
    reason = (
        "Pydantic-only violation in " + normalized + " | " + " ".join(violations[:2])
        + " (CLAUDE.md Code Conventions: model data with Pydantic BaseModel)."
    )
    # Exit 2 blocks the tool call; stderr is surfaced back to Claude.
    print(reason, file=sys.stderr)
    raise SystemExit(2)

allow()
PYEOF
