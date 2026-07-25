---
type: evidence
title: "MODELS.md optfn surrogates table fix matches reality"
description: "Independent verification confirms all 7 claims in the corrected 'Test / optimization surrogates' section (2-Gaussian basis, real function names/registration, LANDSCAPE_REGISTRY, CaseSpec.landscape field, no Rust ModelType, old symbols fully gone)."
resource: "python/oracles/cases.py"
tags: ["strategy:e", "tier:3"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: MODELS.md (docs) -> python/oracles/cases.py + opt_func/*.py (code, phase-2/oracles)
- Verdict: green
- Strategy detail: Tier 3, independent agent verified every individual claim (2-GaussianSpec basis
  in _optfn, DE solver_hint, all 4 @register_landscape decorators, LANDSCAPE_REGISTRY re-export
  chain, CaseSpec.landscape field, absence of any Rust ModelType for these landscapes, and full
  repo-wide absence of the old _PATHOLOGICAL_MODELS/model_hint/ackley_slice/rastrigin_slice symbols).
- Non-overridable: false
