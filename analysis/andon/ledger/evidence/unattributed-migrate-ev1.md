---
type: evidence
title: "Stale trustBlock casing in 2 local benchmark run artifacts fixed and verified"
description: "Re-emitted both stored results.json files through the current BenchReport contract (by_alias=True) to canonicalize their trustBlock sub-fields from snake_case to camelCase; re-ran both previously-failing parametrized roundtrip tests, both now pass."
resource: ".spectrafit_reports/benchmark/2026-06-27_run_023/results.json, .spectrafit_reports/benchmark/2026-06-27_run_024/results.json"
tags: ["strategy:a", "tier:1"]
timestamp: "2026-07-25T00:00:00Z"
---

## Evidence detail

- Wire: gap unattributed-23
- Verdict: green
- Strategy detail: a (functional, self-verified — no independent agent dispatched for this one
  since it's a mechanical data fixup with a direct, deterministic pass/fail test as its own
  proof, and the fix has zero git footprint per the gap doc's scope note). Loaded each file once,
  confirmed `BenchReport.model_validate(raw)` parses the old snake_case shape without error,
  re-emitted via `model.model_dump_json(by_alias=True)`, overwrote each file in place.
  Re-ran `pytest tests/audit/test_audit_results_roundtrip.py::test_results_json_canonical_roundtrip[benchmark/2026-06-27_run_023]`
  and the `run_024` counterpart: both pass (previously both failed with
  "non-canonical results.json... parse→emit changed bytes").
- Non-overridable: false
