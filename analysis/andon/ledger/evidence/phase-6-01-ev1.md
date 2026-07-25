---
type: evidence
title: "PARITY.md PyO3 capability-set correction is accurate"
description: "Independent verification confirms the actual registered PyO3 capability set (lib.rs _core module + _core.pyi) is 6 functions including model_type_wire_strings, the old PARITY.md list really was missing it (checked against the pre-fix committed content), model_type_wire_strings is genuinely consumed directly by test_schema_parity.py with no high-level Python wrapper, and the change is docs-only."
resource: "docs/PARITY.md"
tags: ["strategy:e", "tier:2"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gap phase-6-01 (docs, phase-6/spectrafit-core) — final gap in the brief's 6-phase
  sequence
- Verdict: green
- Strategy detail: e (structural/connectivity), Tier 2 — independent reviewer cross-checked the
  registered PyO3 capability set in two independent files: `crates/spectrafit-core/src/lib.rs`'s
  `#[pymodule] fn _core` registration block (6 `wrap_pyfunction!` calls) and
  `python/spectrafit_core/_core.pyi`'s 6 `def` declarations — both list the same 6 names
  including `model_type_wire_strings`, confirmed not a fabricated name. Confirmed via
  `git show HEAD:docs/PARITY.md` that the pre-fix committed content really listed only 5 names.
  Confirmed `model_type_wire_strings` is called directly as `core.model_type_wire_strings()` in
  `tests/parity/test_schema_parity.py` (two call sites) with no wrapper in
  `python/spectrafit_core/__init__.py`'s `__all__`. Confirmed the diff is scoped entirely to
  `docs/PARITY.md`, no code touched.
- Non-overridable: false
