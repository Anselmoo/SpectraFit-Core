---
type: gap
title: "[High] docs-drift: Test/optimization surrogates table: Python fn column names ackley_slice() / rastrigin_slice(); Rosenbrock/Griewank use a"
description: "python/oracles/opt_func/ackley.py:11 — Test/optimization surrogates table: Python fn column names ackley_slice() / rastrigin_slice(); Rosenbrock/Griewank use a Benchmark model_hint of "rosenbrock"/"griewank"."
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-2]]
- On constraint: false
- Location: `python/oracles/opt_func/ackley.py:11`
- Finding domain: docs-drift
- Suggested fix / explanation: Neither the `ackley_slice()`/`rastrigin_slice()` function names nor the `model_hint` field exist anywhere in the current source; the actual mechanism is the `opt_func.LANDSCAPE_REGISTRY` (private `_ackley` etc.) plus a `landscape` string field on the
- Resolved by: [[evidence/phase-2-02-03-ev1]]
- Proposal: Same edit as phase-2-02 (combined fix, one section). Strategy: e, Tier 3. Blast radius: local+reversible.
