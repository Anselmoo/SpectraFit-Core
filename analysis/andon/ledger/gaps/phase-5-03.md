---
type: gap
title: "[Low] lint-audit: amplitude-is-peak-value"
description: "crates/spectrafit-solver/src/postfit.rs:608 — amplitude-is-peak-value (Amplitude means the peak value at the center, not the area under the curve)"
tags: ["kind:bug", "status:closed", "domain:lint-audit", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-5]]
- On constraint: false
- Location: `crates/spectrafit-solver/src/postfit.rs:608` (pre-refactor line; the comment now
  spans ~626-641 after the Phase 5-02 signature change shifted line numbers)
- Finding domain: lint-audit
- Suggested fix / explanation: Amplitude means the peak value at the center, not the area under
  the curve — a comment in `apply_postfit_guards` claimed 4 models (exp_gaussian,
  skewed_gaussian, doniach_sunjic, true_voigt) all have area-normalised amplitude, violating this
  house rule for 3 of them.
- Resolved by: [[evidence/phase-5-03-ev1]]
- Proposal: Verified against the actual Rust kernels (not just MODELS.md): `crates/
  spectrafit-models/src/voigt_true.rs` eval() divides by `Re[w(z0)]` so `eval(center) ==
  amplitude` EXACTLY — amplitude is definitively a peak value, not an area, contradicting the old
  comment outright. `skewed_gaussian.rs`/`doniach.rs` eval() at x=center also reduce to (a scale
  factor of) `amplitude` directly, with no compensating 1/sigma normalisation — also
  peak/height-scaled, not area. Only `emg.rs` (exp_gaussian/EMG) is genuinely area-normalised (the
  `(γ/2)·exp(...)·erfc(...)` kernel integrates to 1 over all x for γ>0, the standard EMG identity)
  — matching the comment's own cited anti-regression evidence (CX-017), which is specifically
  about exp_gaussian, not the other three. Rewrote the comment to correctly attribute the
  area-normalisation claim to exp_gaussian only, and give the true (narrow/skewed-lineshape)
  rationale for why the other three still warrant the same escape without mischaracterising their
  amplitude semantics. Comment-only change (no logic touched). Strategy: a. Blast radius:
  local+reversible.
