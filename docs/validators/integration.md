---
description: "CLI Validation Middleware Integration Guide — Batch 3 Implementation"
---

# CLI Validation Middleware Integration Guide

## Overview

Batch 3 implements real-time validation of CLI tool inputs before execution. This document explains how validators integrate into the agent tool execution pipeline.

## Architecture

```
Agent Tool Request
    ↓
Check .claude/tool-registry.json for validator
    ↓
Run validator (with 10s timeout)
    ↓
Validator outputs JSON decision
    ↓
Log decision to .claude/audit/validation-decisions.jsonl
    ↓
If allow: Execute tool | If deny: Block operation
    ↓
Log errors (if any) to .claude/audit/validation-errors.log
```

## Integration Points

### Hook registration and audit linkage

The repo now uses a split hook architecture for cloud-batch workflows:

- Registration lives in `.claude/hooks/cloud-batch-observer.json`, which is the VS Code-native discovery point.
- Execution is routed through `.claude/hooks/run-hook.sh` via `.claude/hooks/cloud-batch-observer.sh`.
- Audit output lands in `.claude/audit/enforcement-decisions.jsonl` and `.claude/audit/enforcement-errors.jsonl`.
- The actual hook logic stays in `.claude/scripts/cloud_batch_hook.py`, where it can summarize `.pytest_logs/*.json`, `.spectrafit_reports/*/feedback.json`, and enforce the detached background-run policy for heavy pytest/poe jobs.

This avoids double-registration. In other words, do **not** copy the cloud-batch hook into `.claude/settings.json` as another registered hook entry, because VS Code already loads `.claude/hooks/*.json`. Duplicating the registration there would cause the same policy hook to execute twice.

### 1. Pre-Tool-Execution Hook

Before any agent tool (edit, create, bash) executes:

```bash
# Pseudo-code for agent/CLI layer
if [[ -f ".claude/tool-registry.json" ]]; then
  VALIDATOR=$(jq -r ".validators[\"$TOOL\"].path" .claude/tool-registry.json)
  if [[ -n "$VALIDATOR" && -x "$VALIDATOR" ]]; then
    DECISION=$("$VALIDATOR" "$ARG1" "$ARG2" 2>&1)
    DECISION_JSON=$(echo "$DECISION" | jq -r '.decision')
    if [[ "$DECISION_JSON" == "deny" ]]; then
      # Log and block operation
      log_validation_decision "deny" "$TOOL" "$ARG1" "$DECISION"
      exit 1
    fi
    # Log and allow
    log_validation_decision "allow" "$TOOL" "$ARG1" "$DECISION"
  fi
fi
```

### 2. Validation Decision Logging

After validator runs, log to `.claude/audit/validation-decisions.jsonl`:

```bash
# Helper function for agent/CLI
log_validation_decision() {
  local decision=$1
  local tool=$2
  local path=$3
  local json_result=$4
  
  local entry=$(jq -n \
    --arg ts "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    --arg agent "${AGENT_NAME:-cli-direct}" \
    --arg tool "$tool" \
    --arg path "$path" \
    --arg decision "$decision" \
    --arg reason "$(echo "$json_result" | jq -r '.reason')" \
    --argjson violations "$(echo "$json_result" | jq '.violations')" \
    '{timestamp: $ts, agent: $agent, tool: $tool, path: $path, decision: $decision, reason: $reason, violations: $violations}'
  )
  echo "$entry" >> .claude/audit/validation-decisions.jsonl
}
```

### 3. Error Handling & Fail-Safe

```bash
# If validator crashes or times out, block operation and log error
trap_validator_error() {
  local validator=$1
  local exit_code=$2
  
  if [[ $exit_code -eq 124 ]]; then
    reason="Validator timeout (>10s)"
  elif [[ $exit_code -ne 0 ]] && [[ $exit_code -ne 1 ]]; then
    reason="Validator crashed with exit code $exit_code"
  else
    return 0  # Normal deny, already handled
  fi
  
  # Log error
  echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') ERROR validator=$validator exit_code=$exit_code reason=$reason" >> .claude/audit/validation-errors.log
  
  # Block operation (fail-safe)
  return 1
}
```

## Validator Details

### validate-edit.sh

**When called**: Before `edit` tool modifies an existing file

**Inputs**:
- `$1`: File path (relative to repo root)
- `$2`: Proposed content (full file content)

**Checks**:
- Path traversal detection (blocks `..`)
- File existence (must exist)
- PyO3 boundary checks (Rust files in `src/`)
- Cargo.toml circular dependency detection
- Schema file Pydantic v2 compliance

**Exit codes**:
- `0`: Allow
- `1`: Deny

### validate-create.sh

**When called**: Before `create` tool creates a new file

**Inputs**:
- `$1`: File path (relative to repo root)
- `$2`: File content (full content)

**Checks**:
- Parent directory existence
- Path traversal detection
- File non-existence (must be new)
- Python schema validation (AST syntax check)
- Rust file syntax check (brace matching)
- Markdown frontmatter validation

**Exit codes**:
- `0`: Allow
- `1`: Deny

### validate-bash.sh

**When called**: Before `bash` tool executes a command

**Inputs**:
- `$1`: Command string

**Checks**:
- Dangerous patterns: `rm -rf`, `git push --force`, `sudo`, fork bombs, code injection
- Long-running operations (warnings, but allowed)
- Network operations (warnings, but allowed)
- Side effects (warnings, but allowed)

**Exit codes**:
- `0`: Allow (may include warnings)
- `1`: Deny (dangerous pattern detected)

## Tool Registry Schema

See `.claude/tool-registry.json`:

```json
{
  "version": "1.0",
  "validators": {
    "edit": {"path": "...", "description": "...", "checks": [...], "timeout": "10s"},
    "create": {"path": "...", "description": "...", "checks": [...], "timeout": "10s"},
    "bash": {"path": "...", "description": "...", "dangerous_patterns": [...], "warnings": [...]}
  }
}
```

## Audit Trail Queries

### View all deny decisions in last 24h

```bash
CUTOFF=$(date -u -d "24 hours ago" +'%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -v-24H +'%Y-%m-%dT%H:%M:%SZ')
jq ".[] | select(.timestamp > \"$CUTOFF\" and .decision == \"deny\")" < .claude/audit/validation-decisions.jsonl
```

### View violations by tool

```bash
jq 'group_by(.tool) | map({tool: .[0].tool, denials: map(select(.decision == "deny")) | length})' < .claude/audit/validation-decisions.jsonl
```

### Check validator error rate

```bash
total_decisions=$(wc -l < .claude/audit/validation-decisions.jsonl)
errors=$(wc -l < .claude/audit/validation-errors.log)
echo "Decisions: $total_decisions, Errors: $errors"
```

## Triggering Validators in Practice

### From Python Agent Code

```python
import json
import subprocess

def validate_edit(file_path: str, content: str) -> dict:
    """Call validate-edit.sh and return decision."""
    result = subprocess.run(
        ["./.claude/validators/validate-edit.sh", file_path, content],
        capture_output=True,
        text=True,
        timeout=11  # Give validator 10s + 1s overhead
    )
    try:
        decision = json.loads(result.stdout)
        return decision
    except json.JSONDecodeError:
        return {"decision": "deny", "reason": "Validator output invalid JSON", "violations": ["invalid_output"]}
```

### From CLI

```bash
#!/bin/bash
# Example: before editing a file
FILE_PATH="src/solver.rs"
NEW_CONTENT=$(cat proposed_changes.rs)

DECISION=$(./.claude/validators/validate-edit.sh "$FILE_PATH" "$NEW_CONTENT")
RESULT=$(echo "$DECISION" | jq -r '.decision')

if [[ "$RESULT" == "allow" ]]; then
  echo "$NEW_CONTENT" > "$FILE_PATH"
  echo "Edit approved and applied"
else
  echo "Edit blocked: $(echo "$DECISION" | jq -r '.reason')"
  exit 1
fi
```

## Monitoring & Compliance

### Weekly Audit

```bash
#!/bin/bash
# Check for violations this week
WEEK_AGO=$(date -u -d "7 days ago" +'%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -v-7d +'%Y-%m-%dT%H:%M:%SZ')
echo "=== Violations in last 7 days ==="
jq "select(.timestamp > \"$WEEK_AGO\" and .decision == \"deny\")" < .claude/audit/validation-decisions.jsonl | jq -r '.reason'

echo ""
echo "=== Error Summary ==="
tail -20 .claude/audit/validation-errors.log
```

### Validator Performance

```bash
#!/bin/bash
# Check average validation time
echo "Validator execution frequency by tool:"
jq -s 'group_by(.tool) | map({tool: .[0].tool, count: length})' < .claude/audit/validation-decisions.jsonl | jq -r '.[] | "\(.tool): \(.count) calls"'
```

## Troubleshooting

### Validator Not Found

**Error**: "Validator not found" or operation proceeds without validation

**Solution**: Verify `.claude/tool-registry.json` exists and validator path is correct:
```bash
jq '.validators.edit.path' .claude/tool-registry.json
ls -la $(jq -r '.validators.edit.path' .claude/tool-registry.json)
```

### Validator Crashes or Timeouts

**Error**: "Validator timeout" or "Validator crashed"

**Action**:
1. Check `.claude/audit/validation-errors.log` for details
2. Run validator manually to debug:
   ```bash
   timeout 15 ./.claude/validators/validate-edit.sh "src/test.rs" "test content"
   ```
3. Review validator logic and fix any issues

### Invalid JSON Output

**Error**: "Validator output invalid JSON"

**Solution**: Ensure validator outputs valid JSON. Test:
```bash
./.claude/validators/validate-bash.sh "ls -la" | jq .
```

### Audit Files Growing Too Large

**Action**: Run cleanup script:
```bash
./.claude/audit/cleanup-old-logs.sh
```

## Future Enhancements

- **Performance**: Add caching for repeated file validations
- **Extensibility**: Support custom validators via plugin system
- **Reporting**: Generate compliance reports from audit trail
- **Integration**: Hook into CI/CD for pre-merge validation
- **Feedback**: Collect validator feedback to improve detection rules
