---
type: gap
title: "[High] docs-drift: PyO3 capability-set list incomplete"
description: "crates/spectrafit-core/src/lib.rs:170 — Rust capability set (crates/spectrafit-core/src/lib.rs, declared in _core.pyi): fit, fit_arrays, fit_arrays_numpy (finding evidence snippet truncated mid-list)"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-6]]
- On constraint: true
- Location: `crates/spectrafit-core/src/lib.rs:170` (the `fit` pyfunction — cited as the anchor
  for the module's capability set, not itself the drifted content)
- Finding domain: docs-drift
- Suggested fix / explanation: Verify the actual registered PyO3 capability set (module
  registration function `_core` + `_core.pyi`) against every doc claiming to enumerate it, and
  correct whichever doc is incomplete/stale.
- Resolved by: [[evidence/phase-6-01-ev1]]
- Proposal: Confirmed ground truth first: `_core`'s `#[pymodule]` registration
  (lib.rs:502-515) and `_core.pyi` both list exactly 6 functions — fit, fit_arrays,
  fit_arrays_numpy, evaluate, evaluate_components, model_type_wire_strings — matching each other
  perfectly (no drift there). Then found the actual stale doc via grep: `docs/PARITY.md:91-93`'s
  "Rust capability set" line named only 5 of the 6 (missing `model_type_wire_strings`), while a
  sibling doc (`crates/README.md:22`) already lists the correct full 6 (per DECISIONS.md's own
  2026-07-xx entry noting that exact prior fix) — a case of one doc fixed, a sibling doc missed.
  Fixed PARITY.md to add the missing function and clarify it's consumed directly by
  `tests/parity/test_schema_parity.py` (the Rust↔Python ModelType parity test), not wrapped by a
  high-level Python name — so its absence from the Python-API-mapping table isn't itself drift.
  Docs-only change. Strategy: e (structural/connectivity). Blast radius: local+reversible.
