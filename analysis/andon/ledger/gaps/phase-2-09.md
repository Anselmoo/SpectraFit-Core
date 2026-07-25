---
type: gap
title: "[High] confab:contract-drift: Docstring"
description: "python/oracles/bench_contract.py:290 — Docstring"
tags: ["kind:bug", "status:closed", "domain:confab:contract-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-2]]
- On constraint: false
- Location: `python/oracles/bench_contract.py:290`
- Finding domain: confab:contract-drift
- Suggested fix / explanation: MultiDim / GlobalFit docstrings: "SYNTHETIC — no experimental data; NOT rendered in the production UI (classified `ignored: cut`)" (MultiDim) and "this field is NOT rendered in the production UI (classified `ignored: cut`)" (GlobalFit).
- Resolved by: [[evidence/phase-2-09-ev1]]
- Proposal: Corrected bench_contract.py's MultiDim/GlobalFit docstrings from 'NOT rendered (ignored: cut)' to accurately describe they ARE rendered as Evidence's Native showcases. Strategy: e, Tier 3. Blast radius: local+reversible.
