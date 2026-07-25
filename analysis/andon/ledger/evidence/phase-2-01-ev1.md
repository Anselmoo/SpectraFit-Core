---
type: evidence
title: "CLAUDE.md baseline_solver_id file attribution matches reality"
description: "Independent verification confirms baseline_solver_id is declared in bench_contract.py, not contract.py."
resource: "python/oracles/bench_contract.py"
tags: ["strategy:e", "tier:3"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: CLAUDE.md (docs) -> python/oracles/bench_contract.py (code, phase-2/oracles)
- Verdict: green
- Strategy detail: Tier 3, independent agent confirmed via grep that baseline_solver_id is declared
  at bench_contract.py:946 and contract.py contains zero matches (only _Contract/SolverMeta).
- Non-overridable: false
