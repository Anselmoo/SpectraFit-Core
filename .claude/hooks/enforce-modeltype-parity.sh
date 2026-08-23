#!/usr/bin/env bash
set -euo pipefail

# Capture stdin before the heredoc consumes it.
_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

# PostToolUse, non-blocking: after editing the Python ModelType enum or the Rust
# ModelTypeStr enum, warn (stderr, exit 0) if a model member appears on one side
# without a matching wire string on the other. Best-effort regex; never blocks.
HOOK_STDIN_FILE="$_tmpf" python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PY_FILE = "python/spectrafit_core/models.py"
RS_FILE = "crates/spectrafit-types/src/types.rs"

with open(os.environ["HOOK_STDIN_FILE"], encoding="utf-8") as _fh:
    raw = _fh.read().strip()

if not raw:
    raise SystemExit(0)

try:
    payload = json.loads(raw)
except json.JSONDecodeError:
    raise SystemExit(0)

tool_input = payload.get("tool_input", {}) if isinstance(payload, dict) else {}
path_value = (tool_input.get("file_path") or tool_input.get("path")) if isinstance(tool_input, dict) else None
if not isinstance(path_value, str):
    raise SystemExit(0)

normalized = Path(path_value).as_posix()
if not (normalized.endswith(PY_FILE) or normalized.endswith(RS_FILE)):
    raise SystemExit(0)

# Resolve both files relative to the repo root. PostToolUse runs after the write,
# so reading from disk reflects the just-applied change.
root = Path.cwd()
py_path = root / PY_FILE
rs_path = root / RS_FILE
if not py_path.exists() or not rs_path.exists():
    # Can only compare when both sides are present.
    raise SystemExit(0)


def camel_to_snake(name: str) -> str:
    # Match serde rename_all = "snake_case": insert _ at case boundaries, lower.
    # Handles runs like "2D" -> "2_d"? serde keeps digits attached, but explicit
    # #[serde(rename = ...)] overrides those cases (e.g. gaussian2d), so the
    # heuristic only needs to be right for the un-renamed variants.
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s)
    return s.lower()


def python_values() -> set[str]:
    text = py_path.read_text(encoding="utf-8")
    # Capture inside the ModelType enum block only.
    m = re.search(r"class\s+ModelType\b.*?:(.*?)(?:\nclass\s|\Z)", text, re.DOTALL)
    body = m.group(1) if m else text
    return set(re.findall(r'^[ \t]*[A-Z0-9_]+\s*=\s*"([a-z0-9_]+)"', body, re.MULTILINE))


def rust_values() -> set[str]:
    text = rs_path.read_text(encoding="utf-8")
    m = re.search(r"pub\s+enum\s+ModelTypeStr\s*\{(.*?)\n\}", text, re.DOTALL)
    if not m:
        return set()
    body = m.group(1)
    values: set[str] = set()
    pending_rename: str | None = None
    for line in body.splitlines():
        stripped = line.strip()
        rn = re.search(r'#\[serde\(rename\s*=\s*"([^"]+)"\)\]', stripped)
        if rn:
            pending_rename = rn.group(1)
            continue
        if stripped.startswith("//") or stripped.startswith("#["):
            continue
        var = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*,?\s*$", stripped)
        if var:
            values.add(pending_rename if pending_rename else camel_to_snake(var.group(1)))
            pending_rename = None
    return values


py = python_values()
rs = rust_values()
if not py or not rs:
    raise SystemExit(0)

only_py = sorted(py - rs)
only_rs = sorted(rs - py)
if not only_py and not only_rs:
    raise SystemExit(0)

lines = ["[modeltype-parity] Python ModelType and Rust ModelTypeStr appear to drift:"]
if only_py:
    lines.append(f"  - in Python only (no Rust ModelTypeStr variant): {', '.join(only_py)}")
if only_rs:
    lines.append(f"  - in Rust only (no Python ModelType member): {', '.join(only_rs)}")
lines.append(
    "  Add the matching variant/member and the model_type_to_str arms in "
    "spectrafit-graph + spectrafit-varpro (non-blocking warning; CLAUDE.md "
    "'Adding a New Benchmark Model')."
)
# Non-blocking: warn on stderr, exit 0.
print("\n".join(lines), file=sys.stderr)
raise SystemExit(0)
PYEOF
