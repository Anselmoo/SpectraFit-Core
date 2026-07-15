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
    # Silent exit 0 = proceed. The old decision-allow stdout was invalid hook
    # output (the decision field only accepts approve/block), which is what
    # triggered "Hook JSON output validation failed" on every Edit/Write.
    return


def block(reason: str) -> None:
    # Exit 2 blocks the tool call; stderr is surfaced back to Claude.
    print(reason, file=sys.stderr)
    raise SystemExit(2)


# 13 table headers that form the visual solver-comparison fingerprint.
# NOTE: Block 2 (below) gates on path.name == "render_report.tsx", which no
# longer exists in the greenfield web/ tree — the canonical panel/header
# source of truth is now web/src/panels/registry.tsx, and these exact 13
# thead labels (e.g. "Median ms", "IQR ms", "CV%", "Speedup vs lmfit") were
# restructured out of it. This list is therefore retained as dead reference
# only; the active gate never fires. Re-pointing it requires re-deriving the
# real canonical header set from registry.tsx first — do not assume parity.
REQUIRED_HEADERS: list[str] = [
    "Backend",
    "Median ms",
    "IQR ms",
    "CV%",
    "R\u00b2",           # R²
    "\u03c7\u00b2_red",  # χ²_red
    "MSE",
    "AIC",
    "BIC",
    "n_iter",
    "n_reps",
    "Speedup vs lmfit",
    "Status",
]

# Matches named TypeScript/TSX export declarations.
EXPORT_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?"
    r"(?:function\s*\*?\s*|class\s+|const\s+|let\s+|var\s+|"
    r"type\s+|interface\s+|enum\s+|abstract\s+class\s+)(\w+)",
    re.MULTILINE,
)

ESCAPE_HATCH = "hook: allow-frontend-extension"


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

if not isinstance(payload, dict):
    allow()
    raise SystemExit(0)

tool_name: str = payload.get("tool_name", "")
tool_input = payload.get("tool_input", {})
if not isinstance(tool_input, dict):
    allow()
    raise SystemExit(0)

path_value = tool_input.get("file_path") or tool_input.get("path")
if not isinstance(path_value, str):
    allow()
    raise SystemExit(0)

path = Path(path_value)
norm = path.as_posix()

# Only act on files under web/ (the Vite + React dashboard).
if not norm.startswith("web/"):
    allow()
    raise SystemExit(0)

if tool_name not in {"Edit", "Write"}:
    allow()
    raise SystemExit(0)

# ── Write ────────────────────────────────────────────────────────────────────
if tool_name == "Write":
    content: str = tool_input.get("content", "") or ""
    if ESCAPE_HATCH in content:
        allow()
        raise SystemExit(0)
    if path.exists():
        block(
            f"Frontend soft-freeze: Write to existing '{norm}' is a full rewrite "
            f"(major revision). Use Edit for targeted additive changes. "
            f"To override intentionally, add '// {ESCAPE_HATCH}' in the content."
        )
    # New file creation is additive — allow.
    allow()
    raise SystemExit(0)

# ── Edit ─────────────────────────────────────────────────────────────────────
old: str = tool_input.get("old_string", "") or ""
new: str = tool_input.get("new_string", "") or ""

if ESCAPE_HATCH in old or ESCAPE_HATCH in new:
    allow()
    raise SystemExit(0)

# Block 1 — exported symbol deletion.
deleted = set(EXPORT_RE.findall(old)) - set(EXPORT_RE.findall(new))
if deleted:
    block(
        f"Frontend soft-freeze: Edit to '{norm}' removes exported symbol(s): "
        f"{', '.join(sorted(deleted))}. "
        f"Add new exports without removing existing ones (additive-only). "
        f"To override: add '// {ESCAPE_HATCH}' adjacent to the change."
    )

# Block 2 — required table header removal (render_report.tsx only).
# DEAD GATE: render_report.tsx does not exist under web/ (greenfield rebuild);
# the canonical headers live in web/src/panels/registry.tsx with different
# labels, so this branch never matches. See the REQUIRED_HEADERS note above.
if path.name == "render_report.tsx":
    for header in REQUIRED_HEADERS:
        if header in old and header not in new:
            block(
                f"Frontend soft-freeze: Edit removes required table header '{header}' "
                f"from render_report.tsx. These headers are the visual fingerprint "
                f"for solver comparison and must stay intact. "
                f"To override: add '// {ESCAPE_HATCH}' adjacent to the change."
            )

allow()
PYEOF
