---
type: evidence
title: "PARITY.md model-count fix (11 -> 34) matches reality"
description: "Independent recount confirms ModelTypeStr (Rust) and ModelType (Python) both have exactly 34 variants with byte-for-byte matching wire strings."
resource: "crates/spectrafit-types/src/types.rs"
tags: ["strategy:e", "tier:3"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: docs/PARITY.md (docs) -> crates/spectrafit-types/src/types.rs + python/spectrafit_core/models.py (code)
- Verdict: green
- Strategy detail: Tier 3, independent agent hand-counted both enums. Rust: 34 variants in the
  model_manifest! macro (self-derived via VARIANT_COUNT = ALL.len(), not hand-maintained). Python:
  34 StrEnum members. All 34 wire strings match in declaration order. Bonus finding: Rust's count
  is compile-time auto-derived; Python's is not (kept parallel only by the enforce-modeltype-parity
  hook) — informational, not a new defect in this fix.
- Non-overridable: false
