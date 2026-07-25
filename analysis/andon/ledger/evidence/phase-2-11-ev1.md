---
type: evidence
title: "bench_contract.py PinnedBaseline docstring fix matches reality"
description: "Independent verification confirms PinnedBaseline is genuinely a 4-field subset of write_perf_baseline's 7-key on-disk shape, and _gate_self_perf_check genuinely uses category/baseline_solver_id for cross-context refusal."
resource: "python/oracles/reports.py"
tags: ["strategy:e", "tier:3"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: python/oracles/bench_contract.py (docstring) -> python/oracles/reports.py + cli.py (code, phase-2/oracles)
- Verdict: green
- Strategy detail: Tier 3, independent agent confirmed PinnedBaseline's 4 fields, write_perf_baseline's
  7 on-disk keys, and _gate_self_perf_check's actual use of category/baseline_solver_id (cli.py:628)
  to refuse a cross-context comparison — exactly matching the corrected "subset, not mirror" docstring.
- Non-overridable: false
