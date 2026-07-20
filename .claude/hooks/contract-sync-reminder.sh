#!/usr/bin/env bash
set -euo pipefail

# Capture stdin before the heredoc consumes it.
_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

# PostToolUse, non-blocking: when python/oracles/contract.py is edited,
# remind (stderr, exit 0) to regenerate the three checked-in OpenAPI mirrors.
HOOK_STDIN_FILE="$_tmpf" python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
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

normalized = Path(path_value).as_posix()
# The frozen BenchReport contract is DEFINED in python/oracles/bench_contract.py
# (class BenchReport, served by oracles.api:app). python/oracles/contract.py
# is the shared-leaf module — it holds only SolverMeta, re-exported INTO
# BenchReport — so editing it also changes the wire schema. Fire on either.
if "oracles/bench_contract.py" not in normalized and "oracles/contract.py" not in normalized:
    raise SystemExit(0)

reminder = (
    f"[contract-sync] {normalized} changed — the frozen BenchReport contract "
    "(oracles/bench_contract.py + its oracles/contract.py SolverMeta leaf) feeds "
    "three checked-in OpenAPI mirrors. Regenerate ALL THREE with one command:\n"
    "  uv run poe contract_regen\n"
    "  (regenerates web/src/openapi.gen.ts + web/openapi.snapshot.json + "
    "tests/audit/golden/openapi_normalised.json from one live API instance)\n"
    "(non-blocking reminder; CLAUDE.md 'Regenerate the contract')."
)
# Non-blocking: stderr message, exit 0 so the tool result is unaffected.
print(reminder, file=sys.stderr)
raise SystemExit(0)
PYEOF
