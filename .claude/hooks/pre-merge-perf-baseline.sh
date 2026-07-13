#!/bin/bash
# Invocation status (audit F11, 2026-06-26): MANUAL-ONLY. Not auto-wired to any
# merge gate (absent from .claude/settings.json, .git/hooks/, CI, and poe); runs
# only when invoked by hand via .claude/hooks/run-hook.sh. INDEX.yaml lists it as a
# stream anchor, but enforcement is intentionally manual pending a committed
# pre-push hook or CI job. Do not assume this gate blocks a merge automatically.

################################################################################
# Performance Baseline Checker
#
# Purpose: Ensure that commits touching performance-critical files
#          (solver.rs, crates/spectrafit-solver/) have updated baseline metrics.
#
# Exit codes:
#   0 = Baseline present (if needed) or not needed
#   1 = Baseline missing for performance-critical changes
#
################################################################################

REPO_ROOT=$(git rev-parse --show-toplevel)
VIOLATIONS_FOUND=0

DIAGNOSTIC_BYPASS_RAW="${SPECTRAFIT_PERF_DIAGNOSTIC_BYPASS:-0}"
DIAGNOSTIC_BYPASS=0
if [[ "$DIAGNOSTIC_BYPASS_RAW" == "1" || "$DIAGNOSTIC_BYPASS_RAW" == "true" || "$DIAGNOSTIC_BYPASS_RAW" == "TRUE" || "$DIAGNOSTIC_BYPASS_RAW" == "yes" || "$DIAGNOSTIC_BYPASS_RAW" == "YES" ]]; then
    DIAGNOSTIC_BYPASS=1
fi

AUDIT_LOG_FILE="$REPO_ROOT/.claude/audit/perf-diagnostic-bypass.log"
SPEEDBOAT_COMPLETE=0

audit_bypass_event() {
    local STATUS="$1"
    local DETAIL="$2"
    mkdir -p "$(dirname "$AUDIT_LOG_FILE")"
    printf "%s|status=%s|detail=%s\n" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$STATUS" "$DETAIL" >> "$AUDIT_LOG_FILE"
}

echo "[Perf Baseline Checker] Checking for baseline metrics requirement..."

# List of performance-critical files/paths
PERF_CRITICAL_PATHS=(
    "crates/spectrafit-solver"
    "crates/spectrafit-core/src/lib.rs"
    "python/benchmarkmark/backends"
    "python/benchmarkmark/cases.py"
)

# Check if any perf-critical files are staged/committed
HAS_PERF_CHANGES=0
CHANGED_FILES=""

for PERF_PATH in "${PERF_CRITICAL_PATHS[@]}"; do
    # Check git diff (both staged and unstaged)
    if git diff --name-only --cached | grep -q "$PERF_PATH"; then
        HAS_PERF_CHANGES=1
        CHANGED_FILES="$CHANGED_FILES $(git diff --name-only --cached | grep "$PERF_PATH")"
    fi
    
    if git diff --name-only | grep -q "$PERF_PATH"; then
        HAS_PERF_CHANGES=1
        CHANGED_FILES="$CHANGED_FILES $(git diff --name-only | grep "$PERF_PATH")"
    fi
done

if [ "$HAS_PERF_CHANGES" -eq 0 ]; then
    echo "[Perf Baseline Checker] No performance-critical files changed. PASS."
    exit 0
fi

echo "[Perf Baseline Checker] Performance-critical files detected:"
echo "$CHANGED_FILES" | tr ' ' '\n' | grep . | while read -r FILE; do
    echo "  - $FILE"
done

# Require speedboat report artifacts for benchmark/perf-critical edits
REPORTS_DIR="$REPO_ROOT/.spectrafit_reports"
if [ ! -d "$REPORTS_DIR" ] || [ -z "$(ls -A "$REPORTS_DIR" 2>/dev/null)" ]; then
    echo "VIOLATION: .spectrafit_reports/ is empty — run 'pytest tests/speedboat/' first."
    ((VIOLATIONS_FOUND++))
else
    LATEST_RUN=$(ls -d "$REPORTS_DIR"/[0-9]* 2>/dev/null | sort -n | tail -1)
    if [ -z "$LATEST_RUN" ]; then
        echo "VIOLATION: No numbered speedboat report folder found under .spectrafit_reports/."
        ((VIOLATIONS_FOUND++))
    else
        FEEDBACK_JSON="$LATEST_RUN/feedback.json"
        if [ ! -f "$FEEDBACK_JSON" ]; then
            echo "VIOLATION: Missing feedback.json in latest speedboat run folder: $LATEST_RUN"
            ((VIOLATIONS_FOUND++))
        else
            OVERALL=$(python3 -c "import json; d=json.load(open('$FEEDBACK_JSON')); print(d['gates']['overall'])" 2>/dev/null || echo "False")
            if [ "$OVERALL" != "True" ]; then
                echo "VIOLATION: Gate failed (feedback.gates.overall=false) — see $FEEDBACK_JSON"
                ((VIOLATIONS_FOUND++))
            fi
        fi
    fi
fi

# Check if benchmark/results.json exists and has baseline data
BASELINE_FILE="$REPO_ROOT/benchmark/results.json"
INDEX_FILE="$REPO_ROOT/benchmark/results_index.json"
FEEDBACK_FILE="$REPO_ROOT/benchmark/results_feedback.json"

if [ ! -f "$BASELINE_FILE" ]; then
    echo "VIOLATION: Baseline file not found at $BASELINE_FILE"
    echo "  Required when modifying performance-critical code."
    ((VIOLATIONS_FOUND++))
else
    # Check that baseline has required metrics (median, IQR, N)
    # Parse JSON to check for baseline structure
    BASELINE_HAS_DATA=$(jq '.[] | select(.median != null and .n != null)' "$BASELINE_FILE" 2>/dev/null | wc -l)
    
    if [ "$BASELINE_HAS_DATA" -lt 1 ]; then
        echo "VIOLATION: Baseline file exists but lacks required metrics (median, IQR, N)."
        ((VIOLATIONS_FOUND++))
    else
        echo "[Perf Baseline Checker] Baseline metrics present (checked $(echo "$BASELINE_HAS_DATA") entries)."
    fi
fi

# Prefer explicit aggregate index when available; otherwise discover latest report index.
if [ ! -f "$INDEX_FILE" ]; then
    LATEST_INDEX=$(find "$REPO_ROOT/.spectrafit_reports" -type f -name "results_index.json" 2>/dev/null | sort | tail -n 1)
    if [ -n "$LATEST_INDEX" ]; then
        INDEX_FILE="$LATEST_INDEX"
        FEEDBACK_FILE="$(dirname "$LATEST_INDEX")/results_feedback.json"
    fi
fi

if [ ! -f "$INDEX_FILE" ]; then
    echo "VIOLATION: Missing results_index.json evidence file (expected benchmark/results_index.json or latest .spectrafit_reports/*/results_index.json)."
    ((VIOLATIONS_FOUND++))
else
    echo "[Perf Baseline Checker] Validating benchmark evidence index: $INDEX_FILE"

    HAS_SCENARIOS=$(jq -r 'has("scenarios") and (.scenarios | type == "array") and ((.scenarios | length) > 0)' "$INDEX_FILE" 2>/dev/null)
    HAS_SHORT=$(jq -r '[.scenarios[] | select(.dataset_scale == "short")] | length > 0' "$INDEX_FILE" 2>/dev/null)
    HAS_LARGE=$(jq -r '[.scenarios[] | select(.dataset_scale == "large")] | length > 0' "$INDEX_FILE" 2>/dev/null)
    HAS_COLD_HOT=$(jq -r '[.scenarios[] | select(.timing_mode == "cold_and_hot")] | length > 0' "$INDEX_FILE" 2>/dev/null)
    HAS_HOT_SPEEDUP=$(jq -r '[.scenarios[] | select(.speedup_lmfit_over_spectrafit_hot != null)] | length > 0' "$INDEX_FILE" 2>/dev/null)
    HAS_COLD_SPEEDUP=$(jq -r '[.scenarios[] | select(.timing_mode == "cold_and_hot" and .speedup_lmfit_over_spectrafit_cold != null)] | length > 0' "$INDEX_FILE" 2>/dev/null)

    HAS_SPEEDBOAT_SHORT=$(jq -r '[.scenarios[] | select(.scenario == "regression_smoke" and .dataset_scale == "short")] | length > 0' "$INDEX_FILE" 2>/dev/null)
    HAS_SPEEDBOAT_10K=$(jq -r '[.scenarios[] | select(.scenario == "scaling_10k" and .dataset_scale == "large" and .timing_mode == "cold_and_hot" and .speedup_lmfit_over_spectrafit_hot != null and .speedup_lmfit_over_spectrafit_cold != null)] | length > 0' "$INDEX_FILE" 2>/dev/null)
    HAS_ONLY_SPEEDBOAT_SCENARIOS=$(jq -r '[.scenarios[] | .scenario] | unique | sort == ["regression_smoke","scaling_10k"]' "$INDEX_FILE" 2>/dev/null)

    if [ "$HAS_SPEEDBOAT_SHORT" == "true" ] && [ "$HAS_SPEEDBOAT_10K" == "true" ] && [ "$HAS_ONLY_SPEEDBOAT_SCENARIOS" == "true" ]; then
        SPEEDBOAT_COMPLETE=1
    fi

    if [ "$HAS_SCENARIOS" != "true" ]; then
        echo "VIOLATION: results_index.json does not contain a non-empty scenarios array."
        ((VIOLATIONS_FOUND++))
    fi
    if [ "$HAS_SHORT" != "true" ]; then
        echo "VIOLATION: results_index.json missing short dataset evidence."
        ((VIOLATIONS_FOUND++))
    fi
    if [ "$HAS_LARGE" != "true" ]; then
        echo "VIOLATION: results_index.json missing large dataset evidence."
        ((VIOLATIONS_FOUND++))
    fi
    if [ "$HAS_COLD_HOT" != "true" ]; then
        echo "VIOLATION: results_index.json missing cold_and_hot timing mode evidence."
        ((VIOLATIONS_FOUND++))
    fi
    if [ "$HAS_HOT_SPEEDUP" != "true" ]; then
        echo "VIOLATION: results_index.json missing speedup_lmfit_over_spectrafit_hot values."
        ((VIOLATIONS_FOUND++))
    fi
    if [ "$HAS_COLD_SPEEDUP" != "true" ]; then
        echo "VIOLATION: results_index.json missing speedup_lmfit_over_spectrafit_cold values for cold_and_hot scenarios."
        ((VIOLATIONS_FOUND++))
    fi

    if [ "$DIAGNOSTIC_BYPASS" -eq 1 ] && [ "$SPEEDBOAT_COMPLETE" -ne 1 ]; then
        echo "VIOLATION: diagnostic bypass requested but speedboat evidence is incomplete (need only regression_smoke + scaling_10k with required speedup fields)."
        audit_bypass_event "rejected" "incomplete_speedboat_evidence"
        ((VIOLATIONS_FOUND++))
    fi
fi

if [ ! -f "$FEEDBACK_FILE" ]; then
    echo "VIOLATION: Missing results_feedback.json evidence file (expected benchmark/results_feedback.json or matching .spectrafit_reports run artifact)."
    ((VIOLATIONS_FOUND++))
else
    echo "[Perf Baseline Checker] Validating benchmark feedback gates: $FEEDBACK_FILE"

    HAS_GATES_OBJECT=$(jq -r '.gates | type == "object"' "$FEEDBACK_FILE" 2>/dev/null)
    HAS_SHORT_GATE=$(jq -r '.gates.short_hot_speedup_gt_1 | type == "boolean"' "$FEEDBACK_FILE" 2>/dev/null)
    HAS_LARGE_GATE=$(jq -r '.gates.large_hot_speedup_gt_1 | type == "boolean"' "$FEEDBACK_FILE" 2>/dev/null)
    HAS_COLD_COVERAGE_GATE=$(jq -r '.gates.cold_speedup_coverage_for_cold_and_hot | type == "boolean"' "$FEEDBACK_FILE" 2>/dev/null)
    HAS_OVERALL_GATE=$(jq -r '.gates.overall | type == "boolean"' "$FEEDBACK_FILE" 2>/dev/null)
    OVERALL_PASS=$(jq -r '.gates.overall == true' "$FEEDBACK_FILE" 2>/dev/null)
    HAS_RECOMMENDATIONS=$(jq -r '.recommendations | type == "array" and length > 0' "$FEEDBACK_FILE" 2>/dev/null)

    if [ "$HAS_GATES_OBJECT" != "true" ]; then
        echo "VIOLATION: results_feedback.json missing valid gates object."
        ((VIOLATIONS_FOUND++))
    fi
    if [ "$HAS_SHORT_GATE" != "true" ]; then
        echo "VIOLATION: results_feedback.json missing short_hot_speedup_gt_1 boolean gate."
        ((VIOLATIONS_FOUND++))
    fi
    if [ "$HAS_LARGE_GATE" != "true" ]; then
        echo "VIOLATION: results_feedback.json missing large_hot_speedup_gt_1 boolean gate."
        ((VIOLATIONS_FOUND++))
    fi
    if [ "$HAS_COLD_COVERAGE_GATE" != "true" ]; then
        echo "VIOLATION: results_feedback.json missing cold_speedup_coverage_for_cold_and_hot boolean gate."
        ((VIOLATIONS_FOUND++))
    fi
    if [ "$HAS_OVERALL_GATE" != "true" ]; then
        echo "VIOLATION: results_feedback.json missing overall boolean gate."
        ((VIOLATIONS_FOUND++))
    fi
    if [ "$HAS_RECOMMENDATIONS" != "true" ]; then
        echo "VIOLATION: results_feedback.json missing non-empty recommendations array."
        ((VIOLATIONS_FOUND++))
    fi
    if [ "$OVERALL_PASS" != "true" ]; then
        if [ "$DIAGNOSTIC_BYPASS" -eq 1 ] && [ "$SPEEDBOAT_COMPLETE" -eq 1 ]; then
            echo "[Perf Baseline Checker] WARN: overall gate is false, but diagnostic bypass is enabled with complete speedboat evidence."
            audit_bypass_event "accepted" "overall_false_with_complete_speedboat"
        else
            echo "VIOLATION: results_feedback.json overall gate is false."
            ((VIOLATIONS_FOUND++))
        fi
    elif [ "$DIAGNOSTIC_BYPASS" -eq 1 ] && [ "$SPEEDBOAT_COMPLETE" -eq 1 ]; then
        echo "[Perf Baseline Checker] INFO: diagnostic bypass marker present; overall gate already passed."
        audit_bypass_event "accepted" "overall_true_with_complete_speedboat"
    fi
fi

if [ "$VIOLATIONS_FOUND" -gt 0 ]; then
    echo "[Perf Baseline Checker] FAIL: Baseline validation failed."
    exit 1
else
    echo "[Perf Baseline Checker] PASS: Baseline requirements satisfied."
    exit 0
fi
