---
type: gap
title: "[High] docs-drift: FitOptions <-> FitOptionsSpec field table lists only schema_version, solver, max_iterations, tolerance (all OK)."
description: "python/spectrafit_core/options.py:101 — FitOptions <-> FitOptionsSpec field table lists only schema_version, solver, max_iterations, tolerance (all OK)."
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `python/spectrafit_core/options.py:101`
- Finding domain: docs-drift
- Suggested fix / explanation: Both FitOptions (Python) and FitOptionsSpec (Rust) actually carry 7 fields each, including delta0, max_delta, and eta (added for the Cycle 8.2 trust-region knobs), which are completely absent from the doc's field table. The 4 fields the doc does list
- Resolved by: [[evidence/phase-1-05-ev1]]
- Proposal: Added the 3 missing FitOptions/FitOptionsSpec rows (delta0, max_delta, eta) to docs/PARITY.md's field table. Strategy: e, Tier 3. Blast radius: local+reversible.
