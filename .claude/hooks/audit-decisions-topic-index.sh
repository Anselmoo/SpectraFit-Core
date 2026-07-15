#!/usr/bin/env bash
set -euo pipefail

# PostToolUse — non-blocking warning (exit 0).
# Fires after Edit|Write to DECISIONS.md.
#
# Context: Cycle 7 introduced the topic-index at the top of DECISIONS.md.
# Since then, 12+ ADR entries have landed (Cycle 16/16.A/16.C/D/E/16.F,
# 18/19/20/21/22/23) and not all are indexed. This hook compares new ADR
# headers introduced in this edit against new topic-index lines and warns
# when an ADR header lacks a corresponding index entry.
#
# Bucket keyword heuristics (for the suggestion):
#   CI          : ci, gitlab, kaniko, runner, pipeline, lint, clippy
#   Schema      : schema, migrate, migration, serde, pydantic, openapi, contract
#   Web         : web, playwright, react, vite, frontend, ui, dashboard, chart
#   Solver      : model, kernel, voigt, gauss, nist, v&v, solver, lmfit, jax,
#                 spectrafit, rust, maturin
#   Benchmark   : bench, benchmark, perf, performance, gate, speedup, accuracy
#   Governance  : decision, policy, governance, convention, cycle

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

# Only fire for DECISIONS.md (any location, but typically repo root)
if path.name != "DECISIONS.md":
    raise SystemExit(0)

# Get git diff for DECISIONS.md (post-edit, pre-commit)
try:
    result = subprocess.run(
        ["git", "diff", "DECISIONS.md"],
        capture_output=True, text=True, timeout=15
    )
    diff_text = result.stdout if result.returncode == 0 else ""
except Exception:
    raise SystemExit(0)

if not diff_text.strip():
    # No git-tracked diff yet (e.g. new file or untracked) — try reading the file
    # directly and counting headers vs index lines as a fallback.
    raise SystemExit(0)

# Added lines (strip the leading '+', skip '+++' header)
added_lines = [
    line[1:]
    for line in diff_text.splitlines()
    if line.startswith("+") and not line.startswith("+++")
]

# New ADR headers: lines matching `## [<date/cycle/label>]`
new_adr_headers = [
    line.strip()
    for line in added_lines
    if re.match(r'^## \[', line.strip())
]

if not new_adr_headers:
    # No new ADR headers in this edit — nothing to check.
    raise SystemExit(0)

# New topic-index lines: lines added inside ### <Bucket> sections.
# We identify index entries as non-empty lines added under a ### heading
# that contain a bracket reference like `[Cycle` or `[2026-` or are bullet
# items (`- `) referencing a cycle/date.
topic_index_pattern = re.compile(
    r'^[-*]\s.*(?:\[Cycle|\[20\d\d-|Cycle\s+\d|ADR)', re.IGNORECASE
)
new_index_lines = [
    line.strip()
    for line in added_lines
    if topic_index_pattern.search(line.strip())
]

# Simple heuristic: if new ADR headers > new index lines, warn about the orphans.
orphan_count = len(new_adr_headers) - len(new_index_lines)
if orphan_count <= 0:
    raise SystemExit(0)

# Bucket keyword mapping (lowercase)
BUCKET_KEYWORDS: list[tuple[str, list[str]]] = [
    ("CI", ["ci", "gitlab", "kaniko", "runner", "pipeline", "lint", "clippy", "coverage"]),
    ("Schema", ["schema", "migrate", "migration", "serde", "pydantic", "openapi", "contract", "version"]),
    ("Web", ["web", "playwright", "react", "vite", "frontend", "ui", "dashboard", "chart", "view"]),
    ("Solver", ["model", "kernel", "voigt", "gauss", "nist", "v&v", "solver", "lmfit", "jax",
                "spectrafit", "rust", "maturin", "fitting", "lineshape", "peak"]),
    ("Benchmark", ["bench", "benchmark", "perf", "performance", "gate", "speedup", "accuracy",
                   "regression", "suite", "case"]),
    ("Governance", ["decision", "policy", "governance", "convention", "cycle", "adr", "process"]),
]

def suggest_bucket(header: str) -> str:
    lower = header.lower()
    for bucket, keywords in BUCKET_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return bucket
    return "Governance (default)"

# Only report orphans (those not covered by new index lines)
# Since we can't perfectly pair them, report the last `orphan_count` headers.
orphan_headers = new_adr_headers[len(new_index_lines):]

lines = [
    "[audit-decisions-topic-index] WARNING: New ADR header(s) detected without "
    "a matching topic-index entry.\n",
    f"  {len(new_adr_headers)} new ADR header(s) added, "
    f"{len(new_index_lines)} new index line(s) detected → "
    f"{orphan_count} orphan(s):\n",
]
for hdr in orphan_headers:
    bucket = suggest_bucket(hdr)
    lines.append(f"    {hdr}\n      → suggested bucket: ### {bucket}\n")

lines.append(
    "\n"
    "  The topic-index lives at the top of DECISIONS.md under the\n"
    "  '## Topic Index' section with 6 buckets:\n"
    "    ### CI | ### Schema | ### Web | ### Solver | ### Benchmark | ### Governance\n"
    "\n"
    "  Add a bullet under the appropriate bucket referencing the new ADR,\n"
    "  or accept the drift (this is a non-blocking warning).\n"
)

print("".join(lines), file=sys.stderr)
raise SystemExit(0)
PYEOF
