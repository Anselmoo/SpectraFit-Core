---
type: gap
title: "[High] docs-drift: BenchReport.baseline_solver_id (contract.py) — names which solver defines speedup = 1.0. Default "lmfit". Threaded throu"
description: "python/oracles/bench_contract.py:941 — BenchReport.baseline_solver_id (contract.py) — names which solver defines speedup = 1.0. Default "lmfit". Threaded through build_report, run_suite, run_featured, and the CLI gate."
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-2]]
- On constraint: true
- Location: `python/oracles/bench_contract.py:941`
- Finding domain: docs-drift
- Suggested fix / explanation: The field baseline_solver_id is defined in bench_contract.py, not contract.py (contract.py only holds SolverMeta per CLAUDE.md's own line 283-285). The parenthetical file attribution at line 398 is inconsistent with the correct attribution given two 
- Resolved by: [[evidence/phase-2-01-ev1]]
- Proposal: Corrected CLAUDE.md:398's file attribution (contract.py -> bench_contract.py) for baseline_solver_id. Strategy: e, Tier 3. Blast radius: local+reversible.
