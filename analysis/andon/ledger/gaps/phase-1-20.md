---
type: gap
title: "[Low] code-idiom: unchecked-cd"
description: ".claude/hooks/tests/test_git_hygiene.sh:89 — unchecked-cd"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `.claude/hooks/tests/test_git_hygiene.sh:89`
- Finding domain: code-idiom
- Suggested fix / explanation: Use `cd "$tmp_h" || exit 1` (or `|| return 1` inside functions) at each site so a directory-change failure aborts the test case loudly instead of continuing in the wrong directory.
- Resolved by: [[evidence/phase-1-shell-ev1]]
- Proposal: Added `|| exit 1` to all 9 unchecked `cd` calls in test_git_hygiene.sh's subshells, plus the 1 in test_guard_ledger_freshness.sh (same finding, same class). Strategy: a. Blast radius: local+reversible.
