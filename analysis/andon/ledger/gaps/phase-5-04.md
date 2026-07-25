---
type: gap
title: "[Low] lint-audit: modelsmd-authoritative"
description: "crates/spectrafit-solver/src/postfit.rs:609 — modelsmd-authoritative"
tags: ["kind:bug", "status:closed", "domain:lint-audit", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-5]]
- On constraint: false
- Location: `crates/spectrafit-solver/src/postfit.rs:609` (pre-refactor line; same comment block
  as [[gaps/phase-5-03]])
- Finding domain: lint-audit
- Suggested fix / explanation: MODELS.md is the authoritative source for model parameter
  semantics — a code comment describing model behaviour must match it. The same comment flagged
  by gap 5-03 also violates this rule: MODELS.md's own formula table shows true_voigt's amplitude
  normalised to the peak value (`A · Re[w(z)]/Re[w(z₀)]`), not an area, directly contradicting the
  comment's claim.
- Resolved by: [[evidence/phase-5-03-ev1]] (same fix as gap 5-03 — one comment, two rule
  violations, one edit closes both)
- Proposal: Same fix as [[gaps/phase-5-03]] — verified true_voigt's MODELS.md formula
  (`A · Re[w(z)]/Re[w(z₀)]`) is normalised so the value at center equals `A` exactly, matching the
  Rust kernel (voigt_true.rs) and directly contradicting the old comment's "integrated area, not
  peak height" claim for true_voigt. The corrected comment now matches both MODELS.md's
  authoritative formulas and the actual kernel behaviour for all 4 named models. Strategy: a.
  Blast radius: local+reversible.
