#!/usr/bin/env bash
set -euo pipefail

# Capture stdin before the heredoc consumes it.
_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

python3 - <<PYEOF
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def allow() -> None:
    # Silent exit 0 = proceed; no stdout avoids hook-output schema validation.
    return


with open("$_tmpf", encoding="utf-8") as _fh:
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
is_target = (
    normalized.startswith("python/oracles/")
    or normalized.startswith("tests/")
)
if not is_target or path.suffix != ".py":
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
violations: list[str] = []

if re.search(r'\bpayload\s*\[\s*["\'][^"\']+["\']\s*\]', text):
    violations.append("Use typed payload attributes (payload.field), not payload[\"...\"] indexing.")

if "run_quick_validation_case(" in text and "QuickValidationRunPayload" not in text:
    violations.append("Files calling run_quick_validation_case must use QuickValidationRunPayload typing.")

if "json.loads(" in text and re.search(r'\[[\'"][^\'"]+[\'"]\]', text):
    violations.append("Avoid json.loads + dictionary key indexing for benchmark contracts; validate into Pydantic models.")

if violations:
    reason = "Pydantic-native contract violation in " + normalized + " | " + " ".join(violations[:3])
    # Exit 2 blocks the tool call; stderr is surfaced back to Claude.
    print(reason, file=sys.stderr)
    raise SystemExit(2)

allow()
PYEOF
