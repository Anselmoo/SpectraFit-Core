---
type: gap
title: "[Medium] code-idiom: duplicate-violation-accumulation-logic"
description: ".claude/validators/validate-edit.sh:60 — duplicate-violation-accumulation-logic"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `.claude/validators/validate-edit.sh:60` (and 14 more repeats of the same pattern
  throughout the file)
- Finding domain: code-idiom
- Suggested fix / explanation: Extract a small
  `add_violation() { violations=${violations:+$violations, }"\"$1\""; }` helper (or an array +
  `IFS=,` join).
- Resolved by: [[evidence/unattributed-shell-ev1]]
- Proposal: Added the exact suggested `add_violation()` helper after `json_response()`, then
  replaced all 15 call sites (the repeated `if [[ -n "$violations" ]]; then ...append...; else
  ...set...; fi` blocks, PLUS the ones that used a bare `violations='"X"'` with no append check at
  all — `circular_dependency_detected`, `missing_basemodel`, `missing_or_invalid_scenarios_array`,
  `missing_or_invalid_gates_object` — a latent fragility the finding's own framing implicitly
  covers, since a future added check ahead of one of those bare assignments would silently
  overwrite rather than accumulate) with a single `add_violation "name"` call. Functionally
  tested 4 scenarios (schemas.py with 3 chained violations, results_index.json with 5, including
  the `for gate in ...` loop site, results_feedback.json with 5, and a clean file → allow) via
  git-stash A/B comparison — output byte-identical between original and refactored script across
  all 4 cases, confirming the consolidation preserved every accumulation path including the
  previously bare (non-appending) sites. `bash -n` syntax-clean. Strategy: a (functional
  equivalence test across all accumulation paths). Blast radius: local+reversible.
