#!/bin/bash

################################################################################
# Generate Weekly Enforcement Report
#
# Purpose: Analyze audit trail and generate weekly enforcement report
#
# Usage: generate-weekly-report.sh [start-date] [end-date]
#        or: generate-weekly-report.sh (generates report for current week)
#
# Output: Weekly enforcement report in markdown format
#
################################################################################

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
AUDIT_DIR="${REPO_ROOT}/.claude/audit"

# Determine reporting period
if [ $# -ge 2 ]; then
    START_DATE="$1"
    END_DATE="$2"
else
    # Default: last 7 days
    if command -v date >/dev/null 2>&1; then
        # Try GNU date format first (Linux)
        if date -d "1 day ago" >/dev/null 2>&1; then
            START_DATE=$(date -d "7 days ago" +'%Y-%m-%d')
            END_DATE=$(date +'%Y-%m-%d')
        # Fall back to BSD date format (macOS)
        else
            START_DATE=$(date -u -v-7d +'%Y-%m-%d')
            END_DATE=$(date -u +'%Y-%m-%d')
        fi
    else
        START_DATE="YYYY-MM-DD"
        END_DATE="YYYY-MM-DD"
    fi
fi

# Check if audit files exist
if [ ! -f "${AUDIT_DIR}/enforcement-decisions.jsonl" ] || [ ! -f "${AUDIT_DIR}/enforcement-errors.jsonl" ]; then
    echo "# Weekly Enforcement Report [${START_DATE} to ${END_DATE}]"
    echo ""
    echo "**Status**: No audit data yet. Run hooks to populate audit trail."
    echo ""
    exit 0
fi

# Helper function to count lines (safe for empty files)
count_lines() {
    wc -l < "$1" 2>/dev/null | awk '{print ($1 == 0) ? 0 : $1}'
}

# Count total entries
TOTAL_DECISIONS=$(count_lines "${AUDIT_DIR}/enforcement-decisions.jsonl")
TOTAL_ERRORS=$(count_lines "${AUDIT_DIR}/enforcement-errors.jsonl")
TOTAL_ENTRIES=$((TOTAL_DECISIONS + TOTAL_ERRORS))

# Calculate statistics with jq (if available and files have content)
if command -v jq >/dev/null 2>&1 && [ "$TOTAL_ENTRIES" -gt 0 ]; then
    # Combine files for analysis
    STATS=$(jq -s '
        {
            total: length,
            passes: map(select(.status=="pass")) | length,
            fails: map(select(.status=="fail")) | length,
            avg_time: (map(.duration_ms) // [0] | add / (length // 1) | floor),
            by_hook: group_by(.hook) | map({
                hook: .[0].hook,
                passes: map(select(.status=="pass")) | length,
                fails: map(select(.status=="fail")) | length,
                avg_time: (map(.duration_ms) // [0] | add / (length // 1) | floor),
                timeouts: map(select(.exit_code == 124)) | length
            })
        }
    ' "${AUDIT_DIR}/enforcement-decisions.jsonl" "${AUDIT_DIR}/enforcement-errors.jsonl" 2>/dev/null)
    
    TOTAL=$(echo "$STATS" | jq '.total' 2>/dev/null || echo "$TOTAL_ENTRIES")
    PASSES=$(echo "$STATS" | jq '.passes' 2>/dev/null || echo "$TOTAL_DECISIONS")
    FAILS=$(echo "$STATS" | jq '.fails' 2>/dev/null || echo "$TOTAL_ERRORS")
    AVG_TIME=$(echo "$STATS" | jq '.avg_time' 2>/dev/null || echo "0")
else
    TOTAL=$TOTAL_ENTRIES
    PASSES=$TOTAL_DECISIONS
    FAILS=$TOTAL_ERRORS
    AVG_TIME=0
fi

# Calculate pass rate
if [ "$TOTAL" -gt 0 ]; then
    PASS_RATE=$((PASSES * 100 / TOTAL))
else
    PASS_RATE=0
fi

# Generate report
cat << EOF
# Weekly Enforcement Report [${START_DATE} to ${END_DATE}]

## Summary

- **Total enforcement decisions**: ${TOTAL}
- **Violations blocked**: ${FAILS}
- **Success rate**: ${PASS_RATE}%
- **Average execution time**: ${AVG_TIME} ms

### Status

$(if [ "$PASS_RATE" -ge 95 ]; then echo "✅ **Healthy**: Pass rate >= 95%"; else echo "⚠️ **Attention needed**: Pass rate < 95%, review violations"; fi)

## By Hook

| Hook | Event | Passes | Fails | Pass Rate |
|------|-------|--------|-------|-----------|
EOF

# Add hook statistics
if command -v jq >/dev/null 2>&1 && [ "$TOTAL_ENTRIES" -gt 0 ]; then
    jq -r '.by_hook[] | 
        "| \(.hook) | — | \(.passes) | \(.fails) | " + 
        "\((.passes * 100 / (.passes + .fails) // 100) | floor)% |"' \
        <(echo "$STATS") 2>/dev/null || echo "| [Data unavailable] | — | — | — | — |"
else
    echo "| [Data unavailable] | — | — | — | — |"
fi

cat << EOF

## Violations Analysis

### Exit Codes

EOF

# Show exit code distribution
if command -v jq >/dev/null 2>&1 && [ "$TOTAL_ERRORS" -gt 0 ]; then
    jq -r '.[] | "\(.exit_code // "unknown")"' \
        "${AUDIT_DIR}/enforcement-errors.jsonl" 2>/dev/null | \
        sort | uniq -c | sort -rn | \
        awk '{printf "- Exit code %s: %d occurrences\n", $2, $1}' || echo "- [No violations recorded]"
else
    echo "- No violations recorded"
fi

cat << EOF

### Top Issues

EOF

# Show most common errors
if command -v jq >/dev/null 2>&1 && [ "$TOTAL_ERRORS" -gt 0 ]; then
    jq -r '.[] | "\(.error_message // "unknown")"' \
        "${AUDIT_DIR}/enforcement-errors.jsonl" 2>/dev/null | \
        sort | uniq -c | sort -rn | head -5 | \
        awk '{printf "- %s (%d)\n", substr(\$0, index(\$0,\$2)), \$1}' || echo "- No issues recorded"
else
    echo "- No violations recorded"
fi

cat << EOF

## Recommendations

### Immediate Actions

- [ ] Review top violations and assess patterns
- [ ] Check if violations are legitimate blocks or false positives
- [ ] Monitor timeout incidents (exit code 124)

### For Next Week

- [ ] Archive reports older than 90 days
- [ ] Adjust hook thresholds if needed
- [ ] Update hook documentation based on violations

## Queries

### Generate Fresh Statistics

\`\`\`bash
# Total decisions
wc -l < .claude/audit/enforcement-decisions.jsonl

# Total violations
wc -l < .claude/audit/enforcement-errors.jsonl

# By hook
jq -s 'group_by(.hook) | map({hook: .[0].hook, count: length})' \\
  .claude/audit/enforcement-decisions.jsonl .claude/audit/enforcement-errors.jsonl

# Violations with exit codes
jq '.[] | select(.status=="fail") | {hook, exit_code, error_message}' \\
  .claude/audit/enforcement-errors.jsonl
\`\`\`

---

**Report generated**: $(date -u +'%Y-%m-%dT%H:%M:%SZ')
**Audit trail**: \`.claude/audit/\`

EOF
