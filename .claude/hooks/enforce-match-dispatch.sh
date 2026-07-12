#!/usr/bin/env bash
set -euo pipefail

# Capture stdin before the heredoc consumes it.
_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

# Quoted heredoc (<<'PYEOF') keeps the Python body literal (it contains
# backticks); the temp path is handed in via the HOOK_STDIN_FILE env var.
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
is_target = (
    normalized.startswith("python/extras/")
    or normalized.startswith("python/oracles/")
    or normalized.startswith("tests/")
) and path.suffix == ".py"
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

# Flag if/elif == dispatch chains on a discriminator: two or more equality
# branches comparing the SAME identifier against a value. A lone `if x == y:`
# is fine; a chain (`if x == A: ... elif x == B: ...`) should be `match x:` with
# `case A:` per CLAUDE.md Code Conventions. Anchoring on `^\s*(if|elif) IDENT ==`
# keeps comments and strings (not Python branch lines) out of the match.
branch = re.compile(r"^[ \t]*(?:if|elif)[ \t]+([A-Za-z_][\w.]*)[ \t]*==[ \t]*[^=]")
counts: dict[str, int] = {}
where: dict[str, list[int]] = {}
for lineno, line in enumerate(text.splitlines(), 1):
    m = branch.match(line)
    if m:
        var = m.group(1)
        counts[var] = counts.get(var, 0) + 1
        where.setdefault(var, []).append(lineno)

offenders = {v: n for v, n in counts.items() if n >= 2}
if offenders:
    var, n = max(offenders.items(), key=lambda kv: kv[1])
    locs = ", ".join(f"L{ln}" for ln in where[var][:4])
    reason = (
        f"match/case violation in {normalized}: {n} if/elif {var}==... dispatch "
        f"branches ({locs}). Use 'match {var}:' with 'case ...:' for discriminator "
        f"dispatch (CLAUDE.md Code Conventions). A single 'if x == y:' is fine; "
        f"chains on the same variable are not."
    )
    # Exit 2 blocks the tool call; stderr is surfaced back to Claude.
    print(reason, file=sys.stderr)
    raise SystemExit(2)

allow()
PYEOF
