---
type: evidence
title: "dataset_index non-negative validator closes the Rust usize contract gap"
description: "Directly reproduced the fix's behavior: dataset_index=0/None accepted, dataset_index=-1 rejected with a clear ValidationError; full model test suite (26/26) still passes."
resource: "python/spectrafit_core/models.py"
tags: ["strategy:f", "tier:1"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: python/spectrafit_core/models.py (Python) -> crates/spectrafit-types/src/types.rs (Rust usize boundary)
- Verdict: green
- Strategy detail: f (property/invariant) — directly executed the constructor with dataset_index=0,
  None, and -1: the first two are accepted, -1 raises pydantic.ValidationError with a clear message,
  matching the Rust Option<usize> boundary's actual constraint (cannot deserialize a negative
  integer). tests/unit/spectrafit_core/test_models.py + test_models_python.py (26 tests) still pass,
  confirming no legitimate existing usage was broken by the new validator.
- Non-overridable: false
