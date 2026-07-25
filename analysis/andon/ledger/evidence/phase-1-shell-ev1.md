---
type: evidence
title: "|| exit 1 unchecked-cd fixes pass both shell test suites"
description: "Rung 2 deterministic evidence: test_git_hygiene.sh (21/21) and test_guard_ledger_freshness.sh (5/5) pass after adding || exit 1 to all unchecked cd calls."
resource: ".claude/hooks/tests/test_git_hygiene.sh"
tags: ["strategy:a", "tier:1"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gap phase-1-20 (code, phase-1/claude-hooks) plus the same-class fix in the sibling file
  test_guard_ledger_freshness.sh named in the same original finding
- Verdict: green
- Strategy detail: Rung 2 (rendered-deterministic, real subshell execution). Added `|| exit 1` to
  all 9 unchecked `cd` calls in test_git_hygiene.sh (all inside `( ... )` subshells, so `exit 1` is
  the correct — not `return 1` — form) and the 1 top-level `cd` in test_guard_ledger_freshness.sh.
  Both suites re-run clean: PASS=21 FAIL=0 and PASS=5 FAIL=0 respectively.
- Non-overridable: false
