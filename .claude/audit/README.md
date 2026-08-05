# Audit Trail Documentation

This directory contains persistent audit logs for all hook enforcement decisions and violations. The audit trail provides complete traceability of all automated enforcement actions.

## Files

### 1. `enforcement-decisions.jsonl` — Allowed Operations
**Format**: Newline-delimited JSON (JSONL)

Each line is a JSON object representing a successful hook execution. Fields:
- `timestamp` (string, ISO 8601): When the hook executed
- `hook` (string): Hook name (e.g., `pre-merge-pyO3`)
- `event` (string): Hook event type (e.g., `PreToolUse`, `PostToolUse`, `FileChanged`)
- `status` (string): Always `"pass"` for this file
- `duration_ms` (number): Execution time in milliseconds
- `output` (string): Hook output (truncated to 2KB)

**Example**:
```json
{"timestamp":"2024-05-06T09:15:23Z","hook":"pre-merge-pyO3","event":"PreToolUse","status":"pass","duration_ms":245,"output":"[PyO3 Validator] PASS: All pyfunctions have correct return types."}
{"timestamp":"2024-05-06T09:20:11Z","hook":"pre-merge-schema-sync","event":"FileChanged","status":"pass","duration_ms":128,"output":"[Schema Sync] PASS: Schema file is valid and synchronized."}
```

**Retention**: 90 days (see cleanup policy below)

### 2. `enforcement-errors.jsonl` — Denied/Failed Operations
**Format**: Newline-delimited JSON (JSONL)

Each line represents a failed hook execution or violation. Fields:
- `timestamp` (string, ISO 8601): When the violation occurred
- `hook` (string): Hook name
- `event` (string): Hook event type
- `status` (string): Always `"fail"` for this file
- `exit_code` (number): Hook exit code (0-255, or 124 for timeout)
- `duration_ms` (number): Execution time in milliseconds
- `error_message` (string): Reason for failure
- `output` (string): Hook output before failure (truncated to 2KB)

**Example**:
```json
{"timestamp":"2024-05-06T10:30:45Z","hook":"pre-merge-pyO3","event":"PreToolUse","status":"fail","exit_code":1,"duration_ms":89,"error_message":"Hook execution failed or timed out","output":"VIOLATION: Invalid return type \"Vec<String>\" in src/types.rs:42"}
{"timestamp":"2024-05-06T11:00:00Z","hook":"pre-merge-dag","event":"PostToolUse","status":"fail","exit_code":124,"duration_ms":30000,"error_message":"Hook execution failed or timed out","output":"[DAG Builder] Timeout exceeded"}
```

**Retention**: 90 days (see cleanup policy below)

### 3. `violations-blocked.txt` — Human-Readable Summary
**Format**: Plain text, appended mode

Simple log of all violations in human-readable format. One line per violation.

**Format**: `[TIMESTAMP] [HOOK] VIOLATION: <reason>`

**Example**:
```
[2024-05-06T10:30:45Z] [pre-merge-pyO3] VIOLATION: Exit code: 1
[2024-05-06T11:00:00Z] [pre-merge-dag] VIOLATION: Timeout (30s exceeded)
[2024-05-06T11:15:22Z] [pre-merge-schema-sync] VIOLATION: Exit code: 2
```

**Updated**: Automatically appended each time a violation occurs

## Querying the Audit Trail

### Using jq

All `.jsonl` files are queryable with `jq`:

**Count violations by hook**:
```bash
jq -s 'group_by(.hook) | map({hook: .[0].hook, count: length})' .claude/audit/enforcement-errors.jsonl
```

**Find all timeout violations**:
```bash
jq '.[] | select(.exit_code == 124)' .claude/audit/enforcement-errors.jsonl
```

**List all violations in last 24 hours**:
```bash
CUTOFF=$(date -u -d "24 hours ago" +'%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -v-24H +'%Y-%m-%dT%H:%M:%SZ')
jq ".[] | select(.timestamp > \"$CUTOFF\")" .claude/audit/enforcement-errors.jsonl
```

**Generate pass/fail summary**:
```bash
# Combine both files for total stats
jq -s 'map(.status) | {total: length, passes: map(select(. == "pass")) | length, failures: map(select(. == "fail")) | length}' \
  .claude/audit/enforcement-decisions.jsonl .claude/audit/enforcement-errors.jsonl
```

**Export violations as CSV**:
```bash
jq -r '.[] | [.timestamp, .hook, .event, .exit_code, .error_message] | @csv' \
  .claude/audit/enforcement-errors.jsonl > violations.csv
```

### Using grep

**Find all violations for a specific hook**:
```bash
grep '"hook":"pre-merge-pyO3"' .claude/audit/enforcement-errors.jsonl
```

**Count violations per hook (quick)**:
```bash
grep -o '"hook":"[^"]*"' .claude/audit/enforcement-errors.jsonl | sort | uniq -c
```

## Retention Policy

### Recommended Schedule
- **Daily**: No action (logs accumulate)
- **Weekly**: Review enforcement-report.md, check trends
- **Monthly**: Archive old records (older than 90 days)
- **Quarterly**: Analyze patterns, adjust hook thresholds if needed

### Cleanup Script

Create and run `cleanup-old-logs.sh` to manage retention:

```bash
#!/bin/bash

REPO_ROOT=$(git rev-parse --show-toplevel)
AUDIT_DIR="${REPO_ROOT}/.claude/audit"
RETENTION_DAYS=90

# Backup old records
BACKUP_DIR="${AUDIT_DIR}/.backups"
mkdir -p "$BACKUP_DIR"

# Archive logs older than $RETENTION_DAYS
CUTOFF_DATE=$(date -u -d "${RETENTION_DAYS} days ago" +'%Y-%m-%d' 2>/dev/null || \
               date -u -v-${RETENTION_DAYS}d +'%Y-%m-%d')

for FILE in "${AUDIT_DIR}"/*decisions.jsonl "${AUDIT_DIR}"/*errors.jsonl; do
    if [ -f "$FILE" ]; then
        # Move records older than cutoff to backup
        jq "select(.timestamp < \"${CUTOFF_DATE}\") | @json" "$FILE" >> \
            "${BACKUP_DIR}/$(basename "$FILE").archive"
        
        # Keep only recent records
        jq "select(.timestamp >= \"${CUTOFF_DATE}\")" "$FILE" > "${FILE}.tmp"
        mv "${FILE}.tmp" "$FILE"
    fi
done

echo "Archived logs older than ${CUTOFF_DATE} to ${BACKUP_DIR}"
```

## Integration Points

### Running Hooks

All hooks should be executed via the dispatcher:

```bash
./.claude/hooks/run-hook.sh <hook-name> <event> [args...]
```

The dispatcher handles:
- Timeout protection (30s default, configurable via `HOOK_TIMEOUT` env var)
- Output capture and truncation
- Automatic audit logging
- Fail-safe mode (hook failure = operation denied)

### Accessing Audit Data

From within hook scripts or workflows:

```bash
# Get last 100 decisions
tail -100 .claude/audit/enforcement-decisions.jsonl

# Get most recent error
tail -1 .claude/audit/enforcement-errors.jsonl

# Check total violations today
CUTOFF=$(date +'%Y-%m-%d')
grep "$CUTOFF" .claude/audit/violations-blocked.txt | wc -l
```

### Generating Reports

Use `.github/docs/enforcement-report.md` template to generate weekly reports:

```bash
# Generate report for current week
./.claude/audit/generate-weekly-report.sh > .github/docs/enforcement-report-$(date +'%Y-W%U').md
```

## Data Format Validation

### Validate JSONL files

```bash
# Check if enforcement-decisions.jsonl is valid newline-delimited JSON
jq -e '.' .claude/audit/enforcement-decisions.jsonl >/dev/null 2>&1 && echo "Valid" || echo "Invalid"

# Check for malformed lines
while IFS= read -r line; do
  echo "$line" | jq -e '.' >/dev/null 2>&1 || echo "Invalid line: $line"
done < .claude/audit/enforcement-errors.jsonl
```

## Performance Considerations

- **JSONL format**: One object per line allows efficient append and streaming reads
- **Log rotation**: Implement cleanup script above for 90-day retention
- **Query optimization**: Use `jq -s` only when needed; prefer streaming `jq` for large files
- **Storage**: Typical logs grow ~10KB/week (adjust retention if needed)

## Privacy & Security

- **Stored locally**: Audit logs are stored only in `.claude/audit/` (not committed by default)
- **Output truncation**: Hook output is limited to 2KB to prevent logs from becoming too large
- **No credentials**: Ensure hooks never output secrets to stdout/stderr
- **Access control**: Only repository maintainers should have direct audit log access

## CLI Validation Middleware (Batch 3)

### Overview
CLI validators run **before** agent tools execute, enforcing real-time input validation at the CLI layer.

### Validator Files
- `.claude/validators/validate-edit.sh` — Validates edit tool inputs
- `.claude/validators/validate-create.sh` — Validates create tool inputs
- `.claude/validators/validate-bash.sh` — Validates bash commands

### Integration with Tool Registry

The `.claude/tool-registry.json` maps tools to validators:

```json
{
  "validators": {
    "edit": "./.claude/validators/validate-edit.sh",
    "create": "./.claude/validators/validate-create.sh",
    "bash": "./.claude/validators/validate-bash.sh"
  }
}
```

### CLI Validation Decision Schema

Each validation decision is logged to `.claude/audit/validation-decisions.jsonl`:

```json
{
  "timestamp": "2026-05-06T09:00:00Z",
  "agent": "spectrafit-solver|cli-direct",
  "tool": "edit|create|bash",
  "path": "/path/to/file/or/command",
  "decision": "allow|deny",
  "reason": "Human-readable explanation",
  "violations": ["violation_code_1", "violation_code_2"]
}
```

### Violation Codes

**Edit Tool**: `path_traversal`, `file_not_found`, `pyfunction_return_modified`, `circular_dependency_detected`, `missing_basemodel`, `missing_strict_config`, `uses_any_type`, `schema_migration_violation`

**Create Tool**: `path_traversal`, `file_exists`, `parent_dir_missing`, `missing_basemodel`, `missing_strict_config`, `uses_any_type`, `invalid_python_syntax`, `invalid_rust_syntax`, `missing_frontmatter`, `malformed_frontmatter`

**Bash Tool**: `dangerous_rm_rf`, `dangerous_force_push`, `dangerous_sudo`, `dangerous_fork_bomb`, `code_injection_risk`, `long_running_operation`, `network_operation`, `side_effects_detected`

### Error Scenarios & Handling
- **Validator crash**: Block operation, log to `.claude/audit/validation-errors.log`
- **Validator timeout** (>10s): Block operation (fail-safe)
- **Invalid JSON output**: Treat as deny, log error
- **Missing validator**: Allow operation (degraded mode)

## Troubleshooting

### "Hook file not found"
Verify hook exists at `.claude/hooks/<hook-name>.sh` and is executable.

### "Timeout (30s exceeded)"
Hook took longer than 30 seconds. Either:
1. Optimize the hook to run faster
2. Increase timeout: `HOOK_TIMEOUT=60 ./.claude/hooks/run-hook.sh ...`

### Validator fails with "Invalid JSON"
Check that validator outputs properly formatted JSON. Run validator directly:
```bash
./.claude/validators/validate-edit.sh "src/file.rs" "content"
```

### Audit files growing too large
Implement cleanup script to archive old records (see Retention Policy above).
