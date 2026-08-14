#!/usr/bin/env bash
################################################################################
# Performance / Accuracy Enforcement Hook
#
# Purpose: BLOCK when a benchmark/quick-validation results.json shows that the
#          spectrafit backend is meaningfully slower or less accurate than the
#          lmfit reference. Mirrors CLAUDE.md "Benchmark Backend Comparison
#          Fairness": spectrafit must not be > 2x slower than lmfit.
#
# Claude Code hook contract:
#   - JSON tool-input is read from stdin (ignored here; we inspect results.json).
#   - exit 2 => BLOCK; the reason on stderr is shown to the user.
#   - exit 0 => pass.
#
# Design note: this hook must NEVER crash with a non-2 status. Any internal
# error (missing file, bad JSON, missing keys) traps to exit 0 with a stderr
# note, so a flaky environment never wedges the toolchain. The only blocking
# path is an explicit, well-formed violation.
#
# RESULTS env var: optional override pointing at a specific results.json
# (used for testing). When unset, the newest quick-validation results.json is
# discovered automatically.
################################################################################

# Drain stdin so the producer is not left blocking on a full pipe. We do not
# use the tool-input payload; enforcement is purely results.json-driven.
#
# Note: we intentionally do NOT use `set -e` or an ERR trap. The only command
# allowed to return a non-zero status that matters is python3 (exit 2 = BLOCK);
# every other step is individually guarded with `|| true`/conditionals so an
# environment hiccup can never produce a crash status. python3 absence or any
# unexpected python exit code is normalized to a non-blocking pass below.
cat >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# Locate the applicable results.json.
# ---------------------------------------------------------------------------
RESULTS_FILE="${RESULTS:-}"

if [ -z "$RESULTS_FILE" ]; then
    # Discover repo root (fall back to cwd if not a git repo).
    REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    QV_DIR="$REPO_ROOT/.spectrafit_reports/quick-validation"
    if [ -d "$QV_DIR" ]; then
        # Newest results.json under the quick-validation subtree only.
        RESULTS_FILE="$(find "$QV_DIR" -name results.json 2>/dev/null | xargs -r ls -t 2>/dev/null | head -1)"
    fi
fi

if [ -z "$RESULTS_FILE" ] || [ ! -f "$RESULTS_FILE" ]; then
    # Nothing to enforce.
    exit 0
fi

# ---------------------------------------------------------------------------
# Parse and evaluate with python3. Exit code 2 from python => BLOCK.
# Any other failure inside python is caught and reported as pass (exit 0).
# ---------------------------------------------------------------------------
python3 - "$RESULTS_FILE" <<'PYEOF'
import json
import sys

# Speed rule mirrors CLAUDE.md "Benchmark Backend Comparison Fairness".
SPEED_FACTOR = 2.0

# Accuracy fields are checked defensively: we only flag an accuracy regression
# when BOTH a current error metric AND a baseline error metric are present and
# numeric for the spectrafit backend. Recognized current-error field names
# (first match wins): "rmse", "chisqr", "redchi", "error", "residual".
# Recognized baseline field names (first match wins): "baseline_rmse",
# "baseline_chisqr", "baseline_error", "baseline". If none of these exist the
# accuracy check is silently skipped — no false blocks.
ERROR_FIELDS = ("rmse", "chisqr", "redchi", "error", "residual")
BASELINE_FIELDS = ("baseline_rmse", "baseline_chisqr", "baseline_error", "baseline")


def pass_through(note=None):
    if note:
        print(f"[enforce-perf-accuracy] {note}", file=sys.stderr)
    sys.exit(0)


def as_float(value):
    if isinstance(value, bool):  # bool is an int subclass; reject explicitly.
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def first_present_float(container, field_names):
    if not isinstance(container, dict):
        return None
    for name in field_names:
        if name in container:
            f = as_float(container[name])
            if f is not None:
                return name, f
    return None


def median_ms(backend):
    """Read backend.timing.median_ms defensively."""
    if not isinstance(backend, dict):
        return None
    timing = backend.get("timing")
    if not isinstance(timing, dict):
        return None
    return as_float(timing.get("median_ms"))


def succeeded(backend):
    return isinstance(backend, dict) and backend.get("success") is True


try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        data = json.load(fh)
except (OSError, ValueError):
    pass_through("could not read/parse results.json; passing")

if not isinstance(data, dict):
    pass_through("results.json top-level is not an object; passing")

results = data.get("results")
if not isinstance(results, dict):
    pass_through("results.json has no 'results' object; passing")

speed_violations = []
accuracy_violations = []

for case_id, case in results.items():
    if not isinstance(case, dict):
        continue
    backends = case.get("backends")
    if not isinstance(backends, dict):
        continue

    spectrafit = backends.get("spectrafit")
    lmfit = backends.get("lmfit")

    # --- SPEED ---
    if succeeded(spectrafit) and succeeded(lmfit):
        sf_ms = median_ms(spectrafit)
        lm_ms = median_ms(lmfit)
        if sf_ms is not None and lm_ms is not None and lm_ms > 0:
            if sf_ms > SPEED_FACTOR * lm_ms:
                ratio = sf_ms / lm_ms
                speed_violations.append(
                    f"  [{case_id}] SPEED: spectrafit {sf_ms:.3g} ms is "
                    f"{ratio:.2f}x slower than lmfit {lm_ms:.3g} ms "
                    f"(limit {SPEED_FACTOR:.0f}x)."
                )

    # --- ACCURACY (defensive: only when both fields exist) ---
    if isinstance(spectrafit, dict):
        cur = first_present_float(spectrafit, ERROR_FIELDS)
        base = first_present_float(spectrafit, BASELINE_FIELDS)
        if cur is not None and base is not None:
            cur_name, cur_val = cur
            base_name, base_val = base
            # Lower error is better; flag when current exceeds baseline.
            if cur_val > base_val:
                accuracy_violations.append(
                    f"  [{case_id}] ACCURACY: spectrafit {cur_name}={cur_val:.4g} "
                    f"regressed vs {base_name}={base_val:.4g}."
                )

violations = speed_violations + accuracy_violations
if violations:
    lines = [
        "Perf/accuracy enforcement BLOCKED (CLAUDE.md backend-fairness rule):",
        *violations,
        "",
        "spectrafit must not be > 2x slower than lmfit, nor regress in accuracy "
        "vs baseline. Investigate before proceeding "
        "(see .claude/instructions/perf-accuracy-tdd.md).",
    ]
    print("\n".join(lines), file=sys.stderr)
    sys.exit(2)

sys.exit(0)
PYEOF

# Propagate python's exit code (0 = pass, 2 = block). Any unexpected code is
# normalized to a non-blocking pass to honor the "never crash" contract.
status=$?
if [ "$status" -eq 2 ]; then
    exit 2
fi
exit 0
