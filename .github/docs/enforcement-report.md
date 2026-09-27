# Weekly Enforcement Report [YYYY-MM-DD to YYYY-MM-DD]

> **Template**: Use this markdown to generate weekly enforcement metrics from the audit trail. See sections below for jq queries to populate each metric.

## Summary

- **Total enforcement decisions**: N (all hooks + events)
- **Violations blocked**: N (failed hooks that would deny operations)
- **Average execution time**: X ms (across all hooks)
- **Most common violation**: [Type] (N occurrences this week)
- **Timeout incidents**: N (exit code 124)

### Key Metrics

| Metric | Value | Trend |
|--------|-------|-------|
| Success rate | X% | ↑/↓/→ |
| Avg execution time | X ms | ↑/↓/→ |
| Violations per day | X | ↑/↓/→ |

## By Hook

| Hook | Event | Passes | Fails | Pass Rate | Avg Time |
|------|-------|--------|-------|-----------|----------|
| pre-merge-pyO3 | PreToolUse | N | N | X% | X ms |
| pre-merge-pyO3 | FileChanged | N | N | X% | X ms |
| pre-merge-dag | PostToolUse | N | N | X% | X ms |
| pre-merge-schema-sync | FileChanged | N | N | X% | X ms |
| pre-merge-perf-baseline | PreToolUse | N | N | X% | X ms |

**Interpretation**:
- Pass rate < 95% indicates hook needs tuning or documentation
- Avg time > 5s indicates possible performance regression
- Consistent 100% pass rate indicates hook is well-tuned

## Top Violations This Week

1. **[Violation type]** — N occurrences
   - Example: "Exit code: 1" from pre-merge-pyO3 (invalid return types)
   - Recommendation: Review recent PRs, add developer guide

2. **[Violation type]** — N occurrences
   - Example: "Timeout (30s exceeded)" from pre-merge-dag
   - Recommendation: Optimize DAG builder or increase timeout

3. **[Violation type]** — N occurrences
   - Example: "Hook file not found"
   - Recommendation: Verify hook deployment

## Trend Analysis

### Performance Trends
```
Execution time (last 4 weeks):
Week 1: X ms → Week 2: X ms → Week 3: X ms → Week 4: X ms
```

- **Status**: [Stable / Degrading / Improving]
- **Action**: [None / Investigate / Optimize]

### Violation Trends
```
Violations blocked (last 4 weeks):
Week 1: N → Week 2: N → Week 3: N → Week 4: N
```

- **Status**: [Stable / Increasing / Decreasing]
- **Action**: [None / Increase monitoring / Review policy]

### Hook-by-Hook Trends

| Hook | Week 1 | Week 2 | Week 3 | Week 4 | Trend |
|------|--------|--------|--------|--------|-------|
| pre-merge-pyO3 | N fail | N fail | N fail | N fail | [↑/↓/→] |
| pre-merge-dag | N fail | N fail | N fail | N fail | [↑/↓/→] |
| pre-merge-schema-sync | N fail | N fail | N fail | N fail | [↑/↓/→] |
| pre-merge-perf-baseline | N fail | N fail | N fail | N fail | [↑/↓/→] |

## Recommended Actions

### Threshold Adjustments

- [ ] **pre-merge-pyO3**: Current threshold X — Consider [increasing / decreasing / keeping] based on violation patterns
- [ ] **pre-merge-dag**: Current threshold X — Consider [increasing / decreasing / keeping]
- [ ] **pre-merge-schema-sync**: Current threshold X — Consider [increasing / decreasing / keeping]

### Documentation Updates

- [ ] Add developer guide for [violation type] (N false positives this week)
- [ ] Update README.md with [guidance on X]
- [ ] Create troubleshooting guide for [common issue]

### Exemption Requests

- [ ] Review exemptions granted this week (see `.github/instructions/exemptions.instructions.md`)
- [ ] Consider whether exemptions indicate hook needs tuning

### Monitoring Enhancements

- [ ] [Hook name] timeout rate increasing — monitor next week
- [ ] [Violation type] emerging — add early warning
- [ ] Performance degradation detected — benchmark next week

## Audit Trail Queries

### Generate Summary Statistics

```bash
#!/bin/bash
# Run from repo root
REPO_ROOT=$(git rev-parse --show-toplevel)
AUDIT_DIR="${REPO_ROOT}/.claude/audit"

echo "=== Weekly Enforcement Report ==="
echo ""

# Total decisions and errors
echo "Total decisions (passes):"
wc -l < "${AUDIT_DIR}/enforcement-decisions.jsonl"

echo ""
echo "Total errors (violations):"
wc -l < "${AUDIT_DIR}/enforcement-errors.jsonl"

echo ""
echo "=== By Hook ==="

# Group by hook and count
jq -s 'group_by(.hook) | map({
  hook: .[0].hook,
  passes: map(select(.status=="pass")) | length,
  fails: map(select(.status=="fail")) | length,
  avg_time: (map(.duration_ms) | add / length | round)
})' \
  "${AUDIT_DIR}/enforcement-decisions.jsonl" \
  "${AUDIT_DIR}/enforcement-errors.jsonl" 2>/dev/null || true

echo ""
echo "=== Top Exit Codes ==="

jq -s 'group_by(.exit_code) | 
  map({exit_code: .[0].exit_code, count: length}) | 
  sort_by(.count) | reverse | .[0:5]' \
  "${AUDIT_DIR}/enforcement-errors.jsonl" 2>/dev/null || true

echo ""
echo "=== Timeout Incidents ==="

jq '.[] | select(.exit_code == 124)' \
  "${AUDIT_DIR}/enforcement-errors.jsonl" 2>/dev/null | wc -l
```

### Export for External Analysis

```bash
# Export to CSV for Excel/Sheets
jq -r '[.timestamp, .hook, .status, .duration_ms, .exit_code // "N/A"] | @csv' \
  .claude/audit/enforcement-decisions.jsonl \
  .claude/audit/enforcement-errors.jsonl \
  > enforcement-audit.csv

# Open in your spreadsheet tool
```

### Find Specific Issues

```bash
# Find all violations for pre-merge-pyO3
jq '.[] | select(.hook == "pre-merge-pyO3" and .status == "fail")' \
  .claude/audit/enforcement-errors.jsonl

# Find violations in the last 24 hours
CUTOFF=$(date -u -d "24 hours ago" +'%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || \
         date -u -v-24H +'%Y-%m-%dT%H:%M:%SZ')
jq ".[] | select(.timestamp > \"$CUTOFF\" and .status == \"fail\")" \
  .claude/audit/enforcement-errors.jsonl

# Find patterns in error messages
jq '.[] | select(.error_message | contains("Timeout")) | .hook' \
  .claude/audit/enforcement-errors.jsonl | sort | uniq -c
```

## Implementation Notes

### Creating This Report

1. **Automated**: Set up weekly cron job to generate this report:
   ```bash
   0 9 * * 1 cd /repo && ./.claude/audit/generate-weekly-report.sh > .github/docs/enforcement-report-$(date +'%Y-W%U').md
   ```

2. **Manual**: Run queries above to populate the template each week

3. **CI/CD**: Integrate report generation into your CI pipeline:
   ```yaml
   - name: Generate enforcement report
     run: ./.claude/audit/generate-weekly-report.sh > .github/docs/enforcement-report.md
   ```

### Interpreting Results

- **Pass rate < 95%**: Hook is too strict or has false positives. Review violations and consider adjustment.
- **Pass rate = 100%**: Hook is either perfectly tuned OR not effective. Verify it's actually blocking violations.
- **Avg time > 5s**: Consider performance optimization or splitting into multiple faster hooks.
- **Timeout rate > 5%**: Increase timeout or optimize hook logic.

### Action Items

Violations that should prompt action:
- **Repeated timeout**: Increase `HOOK_TIMEOUT` or optimize hook
- **Repeated exit code X**: Investigate root cause and fix or document
- **Growing trend**: May indicate new codebase patterns or hook needs update

## Archive

Old weekly reports should be moved to `.github/docs/archive/` quarterly:

```bash
mkdir -p .github/docs/archive
find .github/docs -name "enforcement-report-*.md" -mtime +90 -exec mv {} .github/docs/archive/ \;
```

---

**Report generated**: [DATE/TIME]
**Reporting period**: [YYYY-MM-DD to YYYY-MM-DD]
**Audit trail source**: `.claude/audit/`
**Next review**: [DATE]
