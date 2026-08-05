#!/bin/bash
#
# validate-bash.sh — Validates bash commands before execution
# Usage: validate-bash.sh <command>
# Outputs JSON with decision, reason, and violations
# Exit codes: 0 (allow), 1 (deny)

COMMAND="${1:-}"

# Timeout protection (fail-safe if this takes >10s)
if ! timeout 10 bash -c "true" 2>/dev/null; then
  echo '{"decision": "deny", "reason": "Validator timeout", "violations": ["timeout_exceeded"]}'
  exit 1
fi

# Helper functions
json_response() {
  local decision=$1
  local reason=$2
  local exit_code=${3:-0}
  local violations=$4
  
  # Escape reason string for JSON
  reason="${reason//\\/\\\\}"
  reason="${reason//\"/\\\"}"
  reason="${reason//$'\n'/\\n}"
  reason="${reason//$'\r'/\\r}"
  
  echo "{\"decision\": \"$decision\", \"reason\": \"$reason\", \"violations\": [$violations]}"
  exit "$exit_code"
}

# Validate input
if [[ -z "$COMMAND" ]]; then
  json_response "deny" "Command is required" 1 "\"missing_command\""
fi

violations=""
decision="allow"
exit_code=0

# DANGEROUS PATTERNS: Absolute denies (exit 1)
if echo "$COMMAND" | grep -qE "(rm\s+-rf|rm\s+-fr)" 2>/dev/null; then
  json_response "deny" "Destructive rm -rf detected" 1 "\"dangerous_rm_rf\""
fi

if echo "$COMMAND" | grep -qE "git\s+push\s+--force(-with-lease)?" 2>/dev/null; then
  json_response "deny" "Force push detected" 1 "\"dangerous_force_push\""
fi

if echo "$COMMAND" | grep -qE "^\s*sudo\s+" 2>/dev/null; then
  json_response "deny" "Sudo commands not allowed" 1 "\"dangerous_sudo\""
fi

# Fork bomb pattern
if echo "$COMMAND" | grep -qE ":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;" 2>/dev/null; then
  json_response "deny" "Fork bomb detected" 1 "\"dangerous_fork_bomb\""
fi

# /dev/null redirection attacks
if echo "$COMMAND" | grep -qE ">\s*/dev/null.*&&.*rm\s+" 2>/dev/null; then
  json_response "deny" "Suspicious null redirection with rm pattern" 1 "\"suspicious_pattern\""
fi

# eval/exec with variable substitution (code injection risk)
if echo "$COMMAND" | grep -qE "(eval|exec)\s+.*\$\{" 2>/dev/null; then
  json_response "deny" "Dynamic code execution detected" 1 "\"code_injection_risk\""
fi

# Detect long-running operations (allow with warnings)
if echo "$COMMAND" | grep -qE "(cargo\s+build|cargo\s+test|npm\s+install|pip\s+install|docker\s+build|make\s+.*clean|git\s+clone)" 2>/dev/null; then
  if [[ -z "$violations" ]]; then
    violations="\"long_running_operation\""
  else
    violations="$violations, \"long_running_operation\""
  fi
fi

# Network operations that could be slow
if echo "$COMMAND" | grep -qE "(curl|wget|git\s+clone|git\s+fetch)" 2>/dev/null; then
  if [[ -z "$violations" ]]; then
    violations="\"network_operation\""
  else
    violations="$violations, \"network_operation\""
  fi
fi

# Warn on commands with side effects
if echo "$COMMAND" | grep -qE "(git\s+reset|git\s+clean|truncate|dd\s+of=)" 2>/dev/null; then
  if [[ -z "$violations" ]]; then
    violations="\"side_effects_detected\""
  else
    violations="$violations, \"side_effects_detected\""
  fi
fi

# All checks passed - allow
if [[ -z "$violations" ]]; then
  json_response "allow" "Command is safe to execute" 0 ""
else
  json_response "allow" "Command allowed with warnings" 0 "$violations"
fi
