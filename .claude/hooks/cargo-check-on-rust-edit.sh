#!/usr/bin/env bash
set -euo pipefail

# PostToolUse — non-blocking warning (exit 0).
# Fires after any Edit|Write to crates/**/src/*.rs.
# Runs `cargo check --workspace --quiet` to surface cross-crate breakage at
# edit time rather than 30 min later when maturin develop is invoked.
#
# Motivation: Cycle 21 — a new field on FitResultSpec was added but
# crates/spectrafit-varpro/src/solver.rs was not updated; error surfaced via pytest.
# A 3 s warm-cache cargo check catches this immediately.

_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

HOOK_STDIN_FILE="$_tmpf" python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

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

path = Path(path_value)
normalized = path.as_posix()

# Only fire for crates/**/src/*.rs
if path.suffix != ".rs":
    raise SystemExit(0)
# Must be inside crates/ and under src/
parts = path.parts
if not (len(parts) >= 3 and parts[0] == "crates"):
    # Try absolute path: strip repo root prefix if present
    if "/crates/" not in normalized or "/src/" not in normalized:
        raise SystemExit(0)
    if not path.name.endswith(".rs"):
        raise SystemExit(0)
elif "src" not in parts:
    raise SystemExit(0)

# Determine repo root (cargo must run from there)
try:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, timeout=10
    )
    root = result.stdout.strip() if result.returncode == 0 else None
except Exception:
    root = None

if not root:
    raise SystemExit(0)

try:
    proc = subprocess.run(
        ["cargo", "check", "--workspace", "--quiet", "--message-format=short"],
        capture_output=True, text=True, timeout=60, cwd=root
    )
except FileNotFoundError:
    # cargo not on PATH — skip silently
    raise SystemExit(0)
except subprocess.TimeoutExpired:
    print(
        "[cargo-check] WARNING: cargo check timed out after 60 s — "
        "run `cargo check --workspace` manually to verify cross-crate consistency.",
        file=sys.stderr,
    )
    raise SystemExit(0)

if proc.returncode != 0:
    combined = (proc.stdout + proc.stderr).strip()
    # Extract cross-crate dependency hint: look for crate names in error output
    crate_hints = []
    for line in combined.splitlines():
        m = re.search(r'-->\s+(\S+\.rs)', line)
        if m:
            crate_hints.append(m.group(1))
    hint_str = ""
    if crate_hints:
        unique = list(dict.fromkeys(crate_hints))[:3]
        hint_str = f"  Affected file(s): {', '.join(unique)}\n"

    print(
        f"[cargo-check] WARNING: `cargo check --workspace` failed after editing {normalized}.\n"
        f"{hint_str}"
        f"  This edit may have broken a cross-crate dependency (e.g. a struct field added\n"
        f"  in one crate but not yet updated in a dependent crate — cf. Cycle 21 / FitResultSpec).\n"
        f"  Run `cargo check --workspace` locally to see the full error, then fix before\n"
        f"  invoking `maturin develop` or `uv run pytest`.\n"
        f"\n"
        f"  cargo output (first 20 lines):\n"
        + "\n".join(("    " + l) for l in combined.splitlines()[:20]),
        file=sys.stderr,
    )
    # Non-blocking: exit 0 so Claude can decide to fix or proceed.
    raise SystemExit(0)

# Green — silent.
raise SystemExit(0)
PYEOF
