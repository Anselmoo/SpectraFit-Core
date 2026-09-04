#!/usr/bin/env bash
set -euo pipefail

# guard-memory-hazards
# --------------------
# PreToolUse hook on Bash + Read. BLOCKING (exit 2). Codifies the recalibrated
# memory rule after the 2026-06-13 OOM: the hazard is VOLUME, not category.
#
# 2026-06-19 re-architecture (G6/G10): the file guards are now SIZE-BASED, not
# filename-pattern based. The previous version blocked ANY
# `.spectrafit_reports/**/{results,audit}.json` by name regardless of size — which
# false-blocked safe reads (the ~8.4MB audit.json sidecar) and forced MEM_GUARD_OFF
# for genuinely-safe scoped reads. Now a report artifact is blocked only when it
# ACTUALLY exceeds THRESHOLD_BYTES (25MB): the ~46MB results.json is blocked, the
# ~8.4MB audit.json is allowed. Streaming tools (grep/wc/du/stat/ls/sed/awk) are
# never blocked — they don't load the file into memory.
#
# What still OOMs / is guarded:
#   1. workspace-wide `cargo` (compiles all ~11 crates at once)
#        → scope it: `cargo <cmd> -p <crate>` (e.g. -p spectrafit-solver)
#   2. loading a >THRESHOLD report artifact into a tool (cat/head/tail/less/jq,
#      python open(), or the Read tool) — the ~46MB results.json
#        → use the live API: `curl -s localhost:8000/api/report | python3 -c '<extract>'`
#          or the KB sidecars (trust.json / manifest.json).
#   3. an UNBOUNDED benchmark run (`spc-bench run` / `poe benchmark` without --reps),
#      anchored to a real command boundary so a quoted `pgrep "spc-bench run"` arg
#      is NOT matched.
#        → scope with `--reps 1`, or use the cheap run_audit / inject_showcase path.
#
# Bypass for a genuine one-off: prefix the command with `MEM_GUARD_OFF=1`.

_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

HOOK_STDIN_FILE="$_tmpf" python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
import re
import sys

try:
    with open(os.environ["HOOK_STDIN_FILE"]) as fh:
        data = json.load(fh)
except Exception:
    sys.exit(0)  # never break a tool call on a parse failure

tool = data.get("tool_name", "")
ti = data.get("tool_input", {}) or {}

# Size threshold: the real OOM/context hazard is VOLUME. The ~46MB results.json
# is the hazard; the ~8.4MB audit.json sidecar is safe. 25MB splits them cleanly.
THRESHOLD_BYTES = 25 * 1024 * 1024

# Report-artifact path (the only files this guard size-checks). NOT the KB
# sidecars trust.json / manifest.json (always tiny, never matched).
REPORT_PATH = re.compile(r"\.spectrafit_reports/[^\s'\"]*?(?:results|audit)\.json")


def block(msg: str) -> None:
    sys.stderr.write("\U0001f6d1 memory-hazard guard: " + msg + "\n")
    sys.exit(2)


def too_big(path: str) -> bool:
    """True iff the resolved path exists and exceeds THRESHOLD_BYTES.

    A missing/unstattable path returns False — a file that isn't there can't OOM
    a load, and the command will fail (or no-op) on its own terms.
    """
    try:
        p = path if os.path.isabs(path) else os.path.join(os.getcwd(), path)
        return os.path.getsize(p) > THRESHOLD_BYTES
    except OSError:
        return False


_BIG_HINT = (
    "exceeds 25MB — loading it blows memory/context. Use the live API "
    "(curl -s localhost:8000/api/report | python3 -c '<extract>') or the KB sidecars "
    "(trust.json / manifest.json). Streaming (grep/wc/du/stat) is fine at any size; "
    "deliberate? prefix MEM_GUARD_OFF=1."
)

if tool == "Read":
    fp = ti.get("file_path", "")
    if REPORT_PATH.search(fp) and too_big(fp):
        block(f"that report artifact {_BIG_HINT}")
    sys.exit(0)

if tool == "Bash":
    cmd = ti.get("command", "")

    # Explicit, deliberate bypass.
    if re.search(r"\bMEM_GUARD_OFF=1\b", cmd):
        sys.exit(0)

    # 1. workspace-wide cargo (no -p/--package/single-target scoping).
    #    Anchored to real command boundaries so a `cargo test` inside a quoted
    #    grep/echo pattern is NOT matched.
    if (
        re.search(r"(?:^|\n|;|&&|\|\|)\s*(?:nohup\s+|time\s+)?cargo\s+(test|build|check|clippy|nextest)\b", cmd)
        and not re.search(r"(-p\b|--package\b|--bin\b|--lib\b|--example\b|--manifest-path\b|--test\s)", cmd)
    ):
        block(
            "workspace-wide 'cargo' compiles all ~11 crates at once (OOM risk). Scope it: "
            "'cargo <cmd> -p <crate>' (e.g. -p spectrafit-solver). Deliberate full build? "
            "prefix MEM_GUARD_OFF=1."
        )

    # 2. loading a >THRESHOLD report artifact into a memory-loading tool. Size-based:
    #    only blocks when a referenced artifact ACTUALLY exceeds the threshold.
    paths = REPORT_PATH.findall(cmd)
    if paths and (re.search(r"\b(cat|head|tail|less|jq)\b", cmd) or re.search(r"open\s*\(", cmd)):
        oversized = [p for p in paths if too_big(p)]
        if oversized:
            block(f"that loads {oversized[0]} which {_BIG_HINT}")

    # 3. unbounded benchmark run — anchored to a real command boundary so a quoted
    #    `pgrep "spc-bench run"` / `grep "spc-bench run"` ARG is NOT matched.
    if (
        re.search(
            r"(?:^|\n|;|&&|\|\|)\s*(?:nohup\s+|time\s+)?(?:uv\s+run\s+)?(?:spc-bench\s+run|poe\s+benchmark)\b",
            cmd,
        )
        and not re.search(r"--reps\b", cmd)
    ):
        block(
            "unbounded benchmark run (full MC ensemble -> ~46MB results.json + OOM risk). "
            "Scope with '--reps 1', or use the cheap run_audit / inject_showcase single-process "
            "path. Deliberate full run? prefix MEM_GUARD_OFF=1."
        )

    sys.exit(0)

sys.exit(0)
PYEOF
