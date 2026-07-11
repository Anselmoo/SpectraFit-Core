#!/bin/bash
#
# validate-edit.sh — Validates edit tool inputs before execution
# Usage: validate-edit.sh <file_path> <proposed_content>
# Outputs JSON with decision, reason, and violations
# Exit codes: 0 (allow), 1 (deny)

FILE_PATH="${1:-}"
PROPOSED_CONTENT="${2:-}"

# Timeout protection (fail-safe if this takes >10s)
if ! timeout 10 bash -c "true" 2>/dev/null; then
  echo '{"decision": "deny", "reason": "Validator timeout", "violations": ["timeout_exceeded"]}'
  exit 1
fi

# Helper functions
json_response() {
  local decision=$1
  local reason=$2
  local violations=$3
  local exit_code=${4:-0}
  
  # Escape reason string for JSON
  reason="${reason//\\/\\\\}"
  reason="${reason//\"/\\\"}"
  reason="${reason//$'\n'/\\n}"
  reason="${reason//$'\r'/\\r}"
  
  echo "{\"decision\": \"$decision\", \"reason\": \"$reason\", \"violations\": [$violations]}"
  exit "$exit_code"
}

# Validate inputs
if [[ -z "$FILE_PATH" ]]; then
  json_response "deny" "File path is required" "\"missing_file_path\"" 1
fi

if [[ -z "$PROPOSED_CONTENT" ]]; then
  json_response "deny" "Proposed content is required" "\"missing_content\"" 1
fi

# Check for path traversal attacks
if [[ "$FILE_PATH" =~ \.\. ]]; then
  json_response "deny" "Path traversal detected" "\"path_traversal\"" 1
fi

# Check if file exists (edit should operate on existing files)
if [[ ! -f "$FILE_PATH" ]]; then
  json_response "deny" "File does not exist" "\"file_not_found\"" 1
fi

violations=""

# PyO3 boundary check for Rust files in src/
if [[ "$FILE_PATH" =~ ^src/.*\.rs$ ]]; then
  # Check if proposed content contains #[pyfunction] return type modifications
  if grep -q "#\[pyfunction\]" <<< "$PROPOSED_CONTENT" 2>/dev/null; then
    # Extract the function signature after #[pyfunction]
    if echo "$PROPOSED_CONTENT" | grep -A 5 "#\[pyfunction\]" | grep -qE "fn\s+\w+\([^)]*\)\s*->\s*(PyResult|String|i32|f64|bool)"; then
      if [[ -n "$violations" ]]; then
        violations="$violations, \"pyfunction_return_modified\""
      else
        violations="\"pyfunction_return_modified\""
      fi
    fi
  fi
fi

# Cargo.toml dependency cycle check
if [[ "$FILE_PATH" =~ Cargo\.toml$ ]]; then
  # Simple heuristic: check if new dependencies form obvious cycles
  if echo "$PROPOSED_CONTENT" | grep -q "spectrafit-core.*spectrafit-core" 2>/dev/null; then
    violations="\"circular_dependency_detected\""
  fi
fi

# Schema file validation
if [[ "$FILE_PATH" =~ python/spectrafit_core/schemas.*\.py$ ]]; then
  # Check Pydantic v2 compliance: must use BaseModel
  if ! echo "$PROPOSED_CONTENT" | grep -q "BaseModel"; then
    violations="\"missing_basemodel\""
  fi
  
  # Check for strict config
  if ! echo "$PROPOSED_CONTENT" | grep -q "model_config.*strict"; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_strict_config\""
    else
      violations="\"missing_strict_config\""
    fi
  fi
  
  # Check for proper type annotations (no bare 'Any')
  if echo "$PROPOSED_CONTENT" | grep -qE ":\s*Any\s*[,=\)]"; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"uses_any_type\""
    else
      violations="\"uses_any_type\""
    fi
  fi
fi

# Benchmark evidence validation
if [[ "$FILE_PATH" =~ results_index\.json$ ]]; then
  if ! echo "$PROPOSED_CONTENT" | jq -e '.scenarios | type == "array" and length > 0' >/dev/null 2>&1; then
    violations='"missing_or_invalid_scenarios_array"'
  fi

  if ! echo "$PROPOSED_CONTENT" | jq -e '[.scenarios[] | select(.dataset_scale == "short")] | length > 0' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_short_dataset_scale\""
    else
      violations='"missing_short_dataset_scale"'
    fi
  fi

  if ! echo "$PROPOSED_CONTENT" | jq -e '[.scenarios[] | select(.dataset_scale == "large")] | length > 0' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_large_dataset_scale\""
    else
      violations='"missing_large_dataset_scale"'
    fi
  fi

  if ! echo "$PROPOSED_CONTENT" | jq -e '[.scenarios[] | select(.timing_mode == "cold_and_hot")] | length > 0' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_cold_and_hot_timing_mode\""
    else
      violations='"missing_cold_and_hot_timing_mode"'
    fi
  fi

  if ! echo "$PROPOSED_CONTENT" | jq -e '[.scenarios[] | select(.speedup_lmfit_over_spectrafit_hot != null)] | length > 0' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_hot_speedup_fields\""
    else
      violations='"missing_hot_speedup_fields"'
    fi
  fi

  if ! echo "$PROPOSED_CONTENT" | jq -e '[.scenarios[] | select(.timing_mode == "cold_and_hot" and .speedup_lmfit_over_spectrafit_cold == null)] | length == 0' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_cold_speedup_for_cold_and_hot\""
    else
      violations='"missing_cold_speedup_for_cold_and_hot"'
    fi
  fi

fi

if [[ "$FILE_PATH" =~ results_feedback\.json$ ]]; then
  if ! echo "$PROPOSED_CONTENT" | jq -e '.gates | type == "object"' >/dev/null 2>&1; then
    violations='"missing_or_invalid_gates_object"'
  fi

  for gate in short_hot_speedup_gt_1 large_hot_speedup_gt_1 cold_speedup_coverage_for_cold_and_hot overall; do
    if ! echo "$PROPOSED_CONTENT" | jq -e --arg gate "$gate" '.gates[$gate] | type == "boolean"' >/dev/null 2>&1; then
      if [[ -n "$violations" ]]; then
        violations="$violations, \"missing_or_invalid_${gate}\""
      else
        violations="\"missing_or_invalid_${gate}\""
      fi
    fi
  done

  if ! echo "$PROPOSED_CONTENT" | jq -e '.recommendations | type == "array" and length > 0' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_or_empty_recommendations\""
    else
      violations='"missing_or_empty_recommendations"'
    fi
  fi

  if ! echo "$PROPOSED_CONTENT" | jq -e '.gates.overall == true' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"overall_feedback_gate_false\""
    else
      violations='"overall_feedback_gate_false"'
    fi
  fi
fi

# If violations found, deny
if [[ -n "$violations" ]]; then
  json_response "deny" "Schema or boundary violations detected" "$violations" 1
fi

# All checks passed
json_response "allow" "Edit is valid and safe" "" 0
