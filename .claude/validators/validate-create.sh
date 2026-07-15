#!/bin/bash
#
# validate-create.sh — Validates create tool inputs before execution
# Usage: validate-create.sh <file_path> <file_content>
# Outputs JSON with decision, reason, and violations
# Exit codes: 0 (allow), 1 (deny)

FILE_PATH="${1:-}"
FILE_CONTENT="${2:-}"

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

if [[ -z "$FILE_CONTENT" ]]; then
  json_response "deny" "File content is required" "\"missing_content\"" 1
fi

# File should not already exist (create is for new files)
if [[ -f "$FILE_PATH" ]]; then
  json_response "deny" "File already exists" "\"file_exists\"" 1
fi

# Check if parent directory exists
parent_dir=$(dirname "$FILE_PATH")
if [[ ! -d "$parent_dir" ]]; then
  json_response "deny" "Parent directory does not exist" "\"parent_dir_missing\"" 1
fi

# Check for path traversal
if [[ "$FILE_PATH" =~ \.\. ]]; then
  json_response "deny" "Path traversal detected" "\"path_traversal\"" 1
fi

violations=""

# Python schema file validation
if [[ "$FILE_PATH" =~ python/spectrafit_core/schemas.*\.py$ ]]; then
  # Must use Pydantic v2 BaseModel
  if ! echo "$FILE_CONTENT" | grep -q "BaseModel" 2>/dev/null; then
    violations="\"missing_basemodel\""
  fi
  
  # Must have strict config
  if ! echo "$FILE_CONTENT" | grep -q "model_config.*strict" 2>/dev/null; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_strict_config\""
    else
      violations="\"missing_strict_config\""
    fi
  fi
  
  # Check for improper Any usage
  if echo "$FILE_CONTENT" | grep -qE ":\s*Any\s*[,=\)]" 2>/dev/null; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"uses_any_type\""
    else
      violations="\"uses_any_type\""
    fi
  fi
  
  # Validate Python AST (syntax check)
  if ! python3 -c "import ast; ast.parse('''$FILE_CONTENT''')" 2>/dev/null; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"invalid_python_syntax\""
    else
      violations="\"invalid_python_syntax\""
    fi
  fi
fi

# Rust file syntax check (basic check only, skip rustc)
if [[ "$FILE_PATH" =~ \.rs$ ]]; then
  # Basic check: must have matching braces and valid Rust keywords
  brace_count=$(echo "$FILE_CONTENT" | grep -o '{' | wc -l)
  close_brace_count=$(echo "$FILE_CONTENT" | grep -o '}' | wc -l)
  if [[ "$brace_count" != "$close_brace_count" ]]; then
    violations="\"invalid_rust_syntax\""
  fi
fi

# Markdown frontmatter check
if [[ "$FILE_PATH" =~ \.md$ ]]; then
  # If it looks like an instruction or agent file, check frontmatter
  if [[ "$FILE_PATH" =~ (instructions|agents) ]]; then
    # Must start with --- for frontmatter if it's in those directories
    first_line=$(echo "$FILE_CONTENT" | head -1)
    if [[ "$first_line" != "---" ]]; then
      violations="\"missing_frontmatter\""
    fi
    
    # Check basic frontmatter structure (should have closing ---)
    if ! echo "$FILE_CONTENT" | tail -n +2 | grep -q "^---$" 2>/dev/null; then
      if [[ -n "$violations" ]]; then
        violations="$violations, \"malformed_frontmatter\""
      else
        violations="\"malformed_frontmatter\""
      fi
    fi
  fi
fi

# Benchmark evidence validation for newly-created aggregate index files
if [[ "$FILE_PATH" =~ results_index\.json$ ]]; then
  if ! echo "$FILE_CONTENT" | jq -e '.scenarios | type == "array" and length > 0' >/dev/null 2>&1; then
    violations='"missing_or_invalid_scenarios_array"'
  fi

  if ! echo "$FILE_CONTENT" | jq -e '[.scenarios[] | select(.dataset_scale == "short")] | length > 0' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_short_dataset_scale\""
    else
      violations='"missing_short_dataset_scale"'
    fi
  fi

  if ! echo "$FILE_CONTENT" | jq -e '[.scenarios[] | select(.dataset_scale == "large")] | length > 0' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_large_dataset_scale\""
    else
      violations='"missing_large_dataset_scale"'
    fi
  fi

  if ! echo "$FILE_CONTENT" | jq -e '[.scenarios[] | select(.timing_mode == "cold_and_hot")] | length > 0' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_cold_and_hot_timing_mode\""
    else
      violations='"missing_cold_and_hot_timing_mode"'
    fi
  fi

  if ! echo "$FILE_CONTENT" | jq -e '[.scenarios[] | select(.speedup_lmfit_over_spectrafit_hot != null)] | length > 0' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_hot_speedup_fields\""
    else
      violations='"missing_hot_speedup_fields"'
    fi
  fi

  if ! echo "$FILE_CONTENT" | jq -e '[.scenarios[] | select(.timing_mode == "cold_and_hot" and .speedup_lmfit_over_spectrafit_cold == null)] | length == 0' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_cold_speedup_for_cold_and_hot\""
    else
      violations='"missing_cold_speedup_for_cold_and_hot"'
    fi
  fi
fi

if [[ "$FILE_PATH" =~ results_feedback\.json$ ]]; then
  if ! echo "$FILE_CONTENT" | jq -e '.gates | type == "object"' >/dev/null 2>&1; then
    violations='"missing_or_invalid_gates_object"'
  fi

  for gate in short_hot_speedup_gt_1 large_hot_speedup_gt_1 cold_speedup_coverage_for_cold_and_hot overall; do
    if ! echo "$FILE_CONTENT" | jq -e --arg gate "$gate" '.gates[$gate] | type == "boolean"' >/dev/null 2>&1; then
      if [[ -n "$violations" ]]; then
        violations="$violations, \"missing_or_invalid_${gate}\""
      else
        violations="\"missing_or_invalid_${gate}\""
      fi
    fi
  done

  if ! echo "$FILE_CONTENT" | jq -e '.recommendations | type == "array" and length > 0' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"missing_or_empty_recommendations\""
    else
      violations='"missing_or_empty_recommendations"'
    fi
  fi

  if ! echo "$FILE_CONTENT" | jq -e '.gates.overall == true' >/dev/null 2>&1; then
    if [[ -n "$violations" ]]; then
      violations="$violations, \"overall_feedback_gate_false\""
    else
      violations='"overall_feedback_gate_false"'
    fi
  fi
fi

# If violations found, deny
if [[ -n "$violations" ]]; then
  json_response "deny" "Content validation failed" "$violations" 1
fi

# All checks passed
json_response "allow" "File creation is valid and safe" "" 0
