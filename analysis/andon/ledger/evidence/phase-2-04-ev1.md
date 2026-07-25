---
type: evidence
title: "MODELS.md step-param naming fix matches reality"
description: "Independent verification confirms StepSpec declares amplitude/center/sigma directly with no step_height/step_center/step_width alias, and no spectrum_schema module exists."
resource: "python/oracles/cases.py"
tags: ["strategy:e", "tier:3"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: MODELS.md (docs) -> python/oracles/cases.py (code, phase-2/oracles)
- Verdict: green
- Strategy detail: Tier 3, independent agent read StepSpec's full field declaration and grepped
  the whole repo for step_height/step_center/step_width/spectrum_schema — zero hits in live
  source, only in docs/history artifacts (DECISIONS.md's historical ADRs, correctly untouched).
- Non-overridable: false
