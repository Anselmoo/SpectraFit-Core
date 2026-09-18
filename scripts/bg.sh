#!/usr/bin/env bash
# bg.sh — interactive background job launcher for spectrafit-core poe tasks.
#
# Usage
# -----
#   bash scripts/bg.sh                          # interactive select menu
#   bash scripts/bg.sh --menu                   # force interactive menu
#   bash scripts/bg.sh --poe TASK               # direct, CI-safe
#   bash scripts/bg.sh --poe TASK --label NAME  # direct with custom label
#
# All modes delegate submission to scripts/run_pytest_bg.sh (the job engine).
# Check job status with:  bash scripts/check_pytest_bg.sh --job <job_id>
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE="${SCRIPT_DIR}/run_pytest_bg.sh"

# ── Task registry ──────────────────────────────────────────────────────────
# Each entry is "label:poe_task:description"
TASKS=(
    "benchmark:benchmark:Full benchmark suite (JSON/HTML/PDF)"
    "benchmark-publish:benchmark_publish:Publication benchmark (50 reps)"
    "benchmark-speedboat:benchmark_speedboat:Speedboat performance regression tests"
    "qv-all:qv_all:Full quick-validation suite (all cases)"
    "lint:lint:Ruff + ty static checks"
    "self-heal:self_heal:Auto-fix safe issues"
)

# ── Helpers ────────────────────────────────────────────────────────────────
_usage() {
    cat >&2 <<'EOF'
bg.sh — spectrafit-core background job launcher

Usage:
  bg.sh                          interactive menu (default)
  bg.sh --menu                   force interactive menu
  bg.sh --poe TASK [--label X]   submit TASK directly (CI-safe)
  bg.sh --help                   show this message

Available tasks:
EOF
    for entry in "${TASKS[@]}"; do
        IFS=: read -r label task desc <<<"$entry"
        printf "  %-26s  %s\n" "poe $task" "$desc" >&2
    done
}

_submit() {
    local label="$1" task="$2"
    bash "$ENGINE" --label "$label" --poe "$task"
}

# ── Interactive menu ───────────────────────────────────────────────────────
_menu() {
    # Build display list
    local labels=()
    local tasks=()
    local descs=()
    for entry in "${TASKS[@]}"; do
        IFS=: read -r lbl tsk dsc <<<"$entry"
        labels+=("$lbl")
        tasks+=("$tsk")
        descs+=("$dsc")
    done

    # Try fzf first (richer UX), fall back to bash select
    if command -v fzf &>/dev/null; then
        local choices=()
        for i in "${!tasks[@]}"; do
            choices+=("$(printf '%-28s  %s' "poe ${tasks[$i]}" "${descs[$i]}")")
        done
        local picked
        picked=$(printf '%s\n' "${choices[@]}" | fzf \
            --prompt="Submit background job > " \
            --height=40% \
            --border \
            --ansi) || { echo "Aborted." >&2; exit 0; }
        # Extract index by matching the poe task name
        local chosen_task
        chosen_task=$(echo "$picked" | awk '{print $2}')
        local chosen_label=""
        for i in "${!tasks[@]}"; do
            if [[ "${tasks[$i]}" == "$chosen_task" ]]; then
                chosen_label="${labels[$i]}"
                break
            fi
        done
        _submit "$chosen_label" "$chosen_task"
    else
        # Bash select fallback
        echo "Select a task to run in the background:"
        local display=()
        for i in "${!tasks[@]}"; do
            display+=("$(printf '%-28s  %s' "poe ${tasks[$i]}" "${descs[$i]}")")
        done
        PS3="Enter number (q to quit): "
        select choice in "${display[@]}"; do
            if [[ "$REPLY" == "q" ]]; then
                echo "Aborted." >&2; exit 0
            fi
            if [[ -n "$choice" ]]; then
                # Recover index from REPLY (1-based)
                local idx=$(( REPLY - 1 ))
                _submit "${labels[$idx]}" "${tasks[$idx]}"
                break
            fi
            echo "Invalid selection." >&2
        done
    fi
}

# ── Argument parsing ───────────────────────────────────────────────────────
POE_TASK=""
LABEL=""
FORCE_MENU=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --poe)    POE_TASK="${2:?--poe requires a task name}"; shift 2 ;;
        --label)  LABEL="${2:?--label requires a value}"; shift 2 ;;
        --menu)   FORCE_MENU=true; shift ;;
        --help|-h) _usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; _usage; exit 1 ;;
    esac
done

# ── Dispatch ───────────────────────────────────────────────────────────────
if [[ -n "$POE_TASK" ]] && [[ "$FORCE_MENU" == false ]]; then
    # Direct invocation — derive label from task name if not given
    if [[ -z "$LABEL" ]]; then
        LABEL="${POE_TASK//_/-}"
    fi
    _submit "$LABEL" "$POE_TASK"
else
    # Interactive menu (no args, or --menu was passed)
    _menu
fi
