---
type: evidence
title: "ARCHITECTURE.md bounds-enforcement correction is accurate"
description: "Independent verification confirms bounds are enforced by reflection (LmProblem::apply_free_params / reflect_into_bounds), not clamping, called from both solver front-ends' set_params (not residuals()), matching the corrected doc text exactly."
resource: "ARCHITECTURE.md"
tags: ["strategy:e", "tier:2"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gap phase-5-01 (docs, phase-5/spectrafit-solver)
- Verdict: green
- Strategy detail: e (structural/connectivity), Tier 2 (independent reviewer read the actual
  mechanism). Confirmed `reflect_into_bounds` mirrors an overshoot (`2*lo - p` / `2*hi - p`), not
  `.max(lo)`/`.min(hi)` clamping, and parks at the bound on extreme overshoot rather than
  reflecting further. Confirmed the call chain (`apply_free_params` → `set_free_and_tied` →
  both solver front-ends' `set_params`) does not touch `residuals()`/`residuals_into()`, which
  contain no bounds logic at all. New doc text matches the mechanism field-for-field.
- Non-overridable: false
