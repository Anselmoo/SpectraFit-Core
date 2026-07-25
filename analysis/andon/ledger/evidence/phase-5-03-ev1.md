---
type: evidence
title: "amplitude area-vs-peak comment correction verified by independent algebra"
description: "Independent reviewer performed the eval(x=center) substitution algebra for all 4 named models plus the EMG area-normalization identity, confirming only exp_gaussian is genuinely area-normalized and the other three (skewed_gaussian, doniach_sunjic, true_voigt) are peak/height-scaled, matching the corrected comment exactly. Comment-only diff confirmed."
resource: "crates/spectrafit-solver/src/postfit.rs"
tags: ["strategy:a", "tier:2"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gaps phase-5-03 and phase-5-04 (same fix, one comment, two rule violations)
- Verdict: green
- Strategy detail: a (independent reviewer) — did the eval(x=center) substitution algebra
  independently for each model rather than trusting the claim: voigt_true.rs reduces to
  eval(center) == amplitude exactly (peak/peak0 cancels); skewed_gaussian.rs reduces to
  eval(center) == amplitude exactly (g=1, erf(0)=0); doniach.rs reduces to
  eval(center) == amplitude*cos(pi*gamma/2) (a height-scale, not area); emg.rs's formula was
  algebraically confirmed to match the canonical exGaussian PDF term-for-term
  (arg_exp = gamma/2*(2c+gamma*sigma^2-2x)), which is a known closed-form identity integrating to
  exactly `amplitude` over all x for gamma>0 — confirming exp_gaussian's amplitude genuinely is
  the integrated area. Cross-checked against MODELS.md's own formula table and its stated general
  convention (amplitude = peak value, not area) with no area-normalization callout for the other
  three models. Confirmed via diff that only `//`-prefixed comment lines changed inside
  apply_postfit_guards — the guard logic itself (OFF_DOMAIN_R2_FLOOR, detect_off_domain call,
  success/message mutation) is byte-identical before and after.
- Non-overridable: false
