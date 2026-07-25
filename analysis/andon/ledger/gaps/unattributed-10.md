---
type: gap
title: "[Low] code-idiom: long-flat-script-with-duplicated-boilerplate"
description: ".claude/hooks/pre-merge-perf-baseline.sh:76 — long-flat-script-with-duplicated-boilerplate"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `.claude/hooks/pre-merge-perf-baseline.sh:76` (and 17 more repeats of the same
  `echo "VIOLATION: ..."; ((VIOLATIONS_FOUND++))` pattern throughout the 244-line file)
- Finding domain: code-idiom
- Suggested fix / explanation: Factor the repeated `echo VIOLATION + increment` idiom into a
  one-line helper function, and split the jq-based `results_...` validation logic into a separate
  function.
- Resolved by: [[evidence/unattributed-shell-ev1]]
- Proposal: Added a `violation() { echo "VIOLATION: $1"; ((VIOLATIONS_FOUND++)); }` helper (after
  `audit_bypass_event()`) and replaced all 18 call sites with `violation "message"`, including:
  the one two-line message (baseline-file-not-found + its continuation explanation line — kept
  the continuation as a separate plain `echo` after `violation`, since only the primary line is
  the countable violation), and the one site that also calls `audit_bypass_event` alongside the
  echo+increment (reordered to `violation "..."` then `audit_bypass_event ...` — the two are
  independent side effects with no interdependency, so reordering doesn't change the final
  audit-log/stdout/counter state). Did NOT split the jq-based validation into a separate function
  (the suggestion's second half) — the existing structure already reads as one linear sequence of
  independent checks per evidence file, and splitting it into a function would need ~9 jq-derived
  local variables threaded through as parameters/return values for no behavioral gain; judged this
  the conservative stopping point, matching the precedent of prior gaps (e.g. phase-2 gap 12)
  where a further split wasn't worth the risk once the main duplication (the VIOLATION idiom) was
  addressed. Functionally tested 4 distinct scenarios in isolated fake git repos (git-stash A/B
  comparison against the original script): (1) perf-critical file changed, no reports dir at all
  → 4 violations; (2) perf-critical file changed, partial results_index.json/results_feedback.json
  evidence present → 9 violations across both files; (3) no perf-critical files changed → early
  PASS exit 0; (4) `SPECTRAFIT_PERF_DIAGNOSTIC_BYPASS=1` with complete speedboat evidence and
  overall gate false → WARN path + audit-log line written (`status=accepted|
  detail=overall_false_with_complete_speedboat`). All 4 scenarios produced identical output
  (modulo the expected per-run tmpdir path/timestamp) between original and fixed versions.
  `bash -n` syntax-clean. Strategy: a (functional equivalence across all violation/bypass paths).
  Blast radius: local+reversible (file is documented MANUAL-ONLY, not wired into any merge gate).
