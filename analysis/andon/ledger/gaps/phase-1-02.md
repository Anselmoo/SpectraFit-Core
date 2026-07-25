---
type: gap
title: "[High] docs-drift: compose.py # operator-overload composition helpers"
description: "python/spectrafit_core/compose.py:277 — compose.py # operator-overload composition helpers"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `python/spectrafit_core/compose.py:277`
- Finding domain: docs-drift
- Suggested fix / explanation: compose.py implements shape-factory functions plus an explicit builder/accumulator pattern (compose(nodes).bind(expr, to).build()) — there is no operator overloading anywhere in the module or the rest of python/spectrafit_core (grep for __add__/__rad
- Resolved by: [[evidence/phase-1-02-ev1]]
- Proposal: Corrected ARCHITECTURE.md:67's compose.py comment (factory functions + fluent ComposeBuilder, not operator overloading). Strategy: e, Tier 3. Blast radius: local+reversible.
