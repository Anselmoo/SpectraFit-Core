---
type: gap
title: "[Medium] confab:contract-drift: Docstring"
description: "python/oracles/bench_contract.py:651 — Docstring"
tags: ["kind:bug", "status:closed", "domain:confab:contract-drift", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-2]]
- On constraint: false
- Location: `python/oracles/bench_contract.py:651`
- Finding domain: confab:contract-drift
- Suggested fix / explanation: PinnedBaseline: "Mirrors :func:`oracles.reports.write_perf_baseline`'s on-disk shape so the gate's self-vs-self signal is one fetch away in the browser." Fields: run_id, recorded_at, geomean_speedup_vs_baseline, n_cases.
- Resolved by: [[evidence/phase-2-11-ev1]]
- Proposal: Corrected bench_contract.py's PinnedBaseline docstring from 'mirrors' to accurately describe it as a 4-of-7-field subset of write_perf_baseline's on-disk shape. Strategy: e, Tier 3. Blast radius: local+reversible.
