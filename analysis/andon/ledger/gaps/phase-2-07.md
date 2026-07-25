---
type: gap
title: "[High] docs-drift: Reduced / nested-model adequacy. We never fit a reduced (fewer-term) model to full-model data and test whether the simpl"
description: "python/oracles/nested.py:9 — Reduced / nested-model adequacy. We never fit a reduced (fewer-term) model to full-model data and test whether the simplification is statistically adequate (likelihood-ratio / F-test / AIC-BIC). Model"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-2]]
- On constraint: false
- Location: `python/oracles/nested.py:9`
- Finding domain: docs-drift
- Suggested fix / explanation: This exact capability (fit a reduced model, compare to the full/true model via LRT/F-test/AIC/BIC) is fully implemented as wire W9, wired end-to-end from oracles.nested through the contract into a rendered web panel. Git history shows the LIMITATIONS
- Resolved by: [[evidence/phase-2-06-07-08-ev1]]
- Proposal: Removed LIMITATIONS.md's stale 'nested/reduced-model adequacy unmeasured' bullet — W9 fully implements it. Strategy: e, Tier 3. Blast radius: local+reversible.
