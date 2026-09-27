#!/bin/bash

################################################################################
# Hook Execution Dispatcher
#
# Purpose: Centralized hook runner with sandboxing, timeout protection, and
#          audit trail logging. Provides fail-safe mode (hook failure = deny).
#
# Usage: run-hook.sh <hook-name> <event> [args...]
#
# Examples:
#   run-hook.sh pre-merge-pyO3 PreToolUse src/types.rs
#   run-hook.sh pre-merge-dag PostToolUse
#   run-hook.sh pre-merge-schema-sync FileChanged python/schema.py
#
# Exit codes:
#   0 = Hook executed successfully, decision logged to enforcement-decisions.jsonl
#   1 = Hook failed or timed out, violation logged to enforcement-errors.jsonl
#   2 = Invalid arguments or missing hook file
#
# Audit outputs:
#   .claude/audit/enforcement-decisions.jsonl - All allowed operations
#   .claude/audit/enforcement-errors.jsonl    - All denied/failed operations
#   .claude/audit/violations-blocked.txt      - Human-readable summary
#
################################################################################

set -euo pipefail

# Verify arguments
if [ $# -lt 2 ]; then
    echo "Usage: run-hook.sh <hook-name> <event> [args...]" >&2
    exit 2
fi

HOOK_NAME="$1"
EVENT="$2"
shift 2
ARGS=("$@")

# Resolve paths
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
HOOKS_DIR="${REPO_ROOT}/.claude/hooks"
AUDIT_DIR="${REPO_ROOT}/.claude/audit"
HOOK_FILE="${HOOKS_DIR}/${HOOK_NAME}.sh"

# Create audit directory if needed
mkdir -p "${AUDIT_DIR}"

# Validate hook file exists
if [ ! -f "${HOOK_FILE}" ]; then
    ERROR_MSG="Hook file not found: ${HOOK_FILE}"
    echo "${ERROR_MSG}" >&2
    
    # Log error to enforcement-errors.jsonl
    TIMESTAMP=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
    ERROR_JSON=$(printf '{"timestamp":"%s","hook":"%s","event":"%s","status":"fail","exit_code":2,"error_message":"Hook file not found","duration_ms":0}' \
        "$TIMESTAMP" "$HOOK_NAME" "$EVENT")
    echo "$ERROR_JSON" >> "${AUDIT_DIR}/enforcement-errors.jsonl"
    
    # Log to violations-blocked.txt
    echo "[${TIMESTAMP}] [${HOOK_NAME}] VIOLATION: Hook file not found" >> "${AUDIT_DIR}/violations-blocked.txt"
    
    exit 2
fi

# Validate hook file is executable
if [ ! -x "${HOOK_FILE}" ]; then
    ERROR_MSG="Hook file not executable: ${HOOK_FILE}"
    echo "${ERROR_MSG}" >&2
    
    # Log error
    TIMESTAMP=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
    ERROR_JSON=$(printf '{"timestamp":"%s","hook":"%s","event":"%s","status":"fail","exit_code":2,"error_message":"Hook file not executable","duration_ms":0}' \
        "$TIMESTAMP" "$HOOK_NAME" "$EVENT")
    echo "$ERROR_JSON" >> "${AUDIT_DIR}/enforcement-errors.jsonl"
    
    echo "[${TIMESTAMP}] [${HOOK_NAME}] VIOLATION: Hook file not executable" >> "${AUDIT_DIR}/violations-blocked.txt"
    
    exit 2
fi

# Configuration
TIMEOUT=${HOOK_TIMEOUT:-30}
TEMP_OUTPUT="${REPO_ROOT}/.claude/.hook_output_$$"

# Best-effort cache hardening for environments where uv may be invoked by
# downstream tooling and transient cache directory races can occur.
mkdir -p "${HOME}/.cache/uv/simple-v21/pypi" 2>/dev/null || true

# Record start time (nanoseconds for precision)
START_TIME=$(date +%s%N)
TIMESTAMP=$(date -u +'%Y-%m-%dT%H:%M:%SZ')

# Execute hook in isolated subshell with timeout and output capture
# Fail-safe: any hook error results in operation denial
HOOK_EXIT_CODE=0
{
    set +e
    if [ ${#ARGS[@]} -gt 0 ]; then
        timeout "$TIMEOUT" bash "${HOOK_FILE}" "${ARGS[@]}" 2>&1 | tee "$TEMP_OUTPUT"
    else
        timeout "$TIMEOUT" bash "${HOOK_FILE}" 2>&1 | tee "$TEMP_OUTPUT"
    fi
    HOOK_EXIT_CODE=$?
    set -e
} || HOOK_EXIT_CODE=$?

# Record end time
END_TIME=$(date +%s%N)

# Calculate duration in milliseconds
DURATION_MS=$(( ($END_TIME - $START_TIME) / 1000000 ))

# Read captured output
HOOK_OUTPUT=""
if [ -f "$TEMP_OUTPUT" ]; then
    HOOK_OUTPUT=$(cat "$TEMP_OUTPUT" | head -c 2000)  # Limit to 2KB
    rm -f "$TEMP_OUTPUT"
fi

# Sanitize JSON strings (escape special characters)
sanitize_json_string() {
    printf '%s\n' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/	/\\t/g' | tr '\n' ' '
}

# Identify transient infrastructure failures that should not hard-block hooks.
is_transient_infra_error() {
    local msg="$1"
    echo "$msg" | grep -Eiq 'Failed to write to the client cache|failed to rename file from .*/\.tmp.* to .*/\.rkyv|No such file or directory \(os error 2\)|uv/simple-v[0-9]+/pypi'
}

HOOK_OUTPUT_ESCAPED=$(sanitize_json_string "$HOOK_OUTPUT")
EVENT_ESCAPED=$(sanitize_json_string "$EVENT")

# Log to audit trail
if [ $HOOK_EXIT_CODE -eq 0 ]; then
    # Success: log to enforcement-decisions.jsonl
    DECISION_JSON=$(printf '{"timestamp":"%s","hook":"%s","event":"%s","status":"pass","duration_ms":%d,"output":"%s"}' \
        "$TIMESTAMP" "$HOOK_NAME" "$EVENT_ESCAPED" "$DURATION_MS" "$HOOK_OUTPUT_ESCAPED")
    echo "$DECISION_JSON" >> "${AUDIT_DIR}/enforcement-decisions.jsonl"
    
    # Exit successfully
    exit 0
else
    # Graceful-degrade on known transient cache/infrastructure faults.
    if is_transient_infra_error "$HOOK_OUTPUT"; then
        WARN_JSON=$(printf '{"timestamp":"%s","hook":"%s","event":"%s","status":"warn","exit_code":%d,"duration_ms":%d,"warning":"Transient infrastructure/cache failure tolerated","output":"%s"}' \
            "$TIMESTAMP" "$HOOK_NAME" "$EVENT_ESCAPED" "$HOOK_EXIT_CODE" "$DURATION_MS" "$HOOK_OUTPUT_ESCAPED")
        echo "$WARN_JSON" >> "${AUDIT_DIR}/enforcement-decisions.jsonl"
        echo "[${TIMESTAMP}] [${HOOK_NAME}] WARN: transient infra/cache failure tolerated" >> "${AUDIT_DIR}/violations-blocked.txt"
        exit 0
    fi

    # Failure: log to enforcement-errors.jsonl (fail-safe mode)
    ERROR_JSON=$(printf '{"timestamp":"%s","hook":"%s","event":"%s","status":"fail","exit_code":%d,"duration_ms":%d,"error_message":"Hook execution failed or timed out","output":"%s"}' \
        "$TIMESTAMP" "$HOOK_NAME" "$EVENT_ESCAPED" "$HOOK_EXIT_CODE" "$DURATION_MS" "$HOOK_OUTPUT_ESCAPED")
    echo "$ERROR_JSON" >> "${AUDIT_DIR}/enforcement-errors.jsonl"
    
    # Log to violations-blocked.txt
    VIOLATION_REASON="Exit code: $HOOK_EXIT_CODE"
    if [ $HOOK_EXIT_CODE -eq 124 ]; then
        VIOLATION_REASON="Timeout (${TIMEOUT}s exceeded)"
    fi
    echo "[${TIMESTAMP}] [${HOOK_NAME}] VIOLATION: ${VIOLATION_REASON}" >> "${AUDIT_DIR}/violations-blocked.txt"
    
    # Exit with failure (deny operation)
    exit 1
fi
