---
type: gap
title: "[High] docs-drift: The four multimodal functions (Ackley/Rastrigin/Rosenbrock/Griewank) are not native kernels: in the benchmark they are a"
description: "python/oracles/cases.py:885 — The four multimodal functions (Ackley/Rastrigin/Rosenbrock/Griewank) are not native kernels: in the benchmark they are approximated by a fixed 3-Gaussian basis solved by the global (DE) optimizer, see"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-2]]
- On constraint: false
- Location: `python/oracles/cases.py:885`
- Finding domain: docs-drift
- Suggested fix / explanation: The current code fits a 2-Gaussian surrogate (not 3), declared declaratively in cases.py, and `_PATHOLOGICAL_MODELS` no longer exists anywhere in the codebase — it was deleted during the benchmark rebuild and the doc was never resynced.
- Resolved by: [[evidence/phase-2-02-03-ev1]]
- Proposal: Rewrote MODELS.md's optfn surrogates table: 3-Gaussian -> 2-Gaussian, removed the deleted _PATHOLOGICAL_MODELS symbol, replaced the fictional model_hint/ackley_slice() names with the real @register_landscape/LANDSCAPE_REGISTRY/CaseSpec.landscape mechanism. Strategy: e, Tier 3. Blast radius: local+reversible.
