---
type: evidence
title: "PARITY.md FitOptions field table fix (4 -> 7 rows) matches reality"
description: "Independent verification confirms all 7 FitOptions/FitOptionsSpec fields exist and type-match on both sides, with the 3 new rows backed by a real cross-boundary test."
resource: "python/spectrafit_core/options.py"
tags: ["strategy:e", "tier:3"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: docs/PARITY.md (docs) -> python/spectrafit_core/options.py + crates/spectrafit-types/src/types.rs (code)
- Verdict: green
- Strategy detail: Tier 3, independent agent confirmed field-by-field type compatibility for all
  7 fields (schema_version/solver/max_iterations/tolerance/delta0/max_delta/eta), and additionally
  found tests/unit/spectrafit_core/test_tr_knobs.py:79-146 exercises delta0/max_delta/eta with real
  non-default values through the actual Rust fit() boundary — stronger evidence than a static type
  comparison alone.
- Non-overridable: false
