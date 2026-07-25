---
type: evidence
title: "PARITY.md FitResult field-count fix (19 -> 25) matches reality"
description: "Independent recount confirms FitResult (Python) and FitResultSpec (Rust) both have exactly 25 fields, one-for-one, plus DatasetSlice/DatasetSliceSpec's 5 fields."
resource: "python/spectrafit_core/result.py"
tags: ["strategy:e", "tier:3"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: docs/PARITY.md (docs) -> python/spectrafit_core/result.py + crates/spectrafit-types/src/types.rs (code)
- Verdict: green
- Strategy detail: Tier 3, independent agent hand-counted both classes/structs field-by-field,
  correctly excluding the `params` property alias (not a declared field). 25=25 with identical
  names/order on both sides; DatasetSlice/DatasetSliceSpec 5=5 confirmed too.
- Non-overridable: false
