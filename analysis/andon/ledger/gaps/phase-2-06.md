---
type: gap
title: "[High] docs-drift: multidim / time-resolved showcases are deferred. The contract carries `multidim` (2-D Gaussian map) and `time_resolved` "
description: "python/oracles/bench_contract.py:506 — multidim / time-resolved showcases are deferred. The contract carries `multidim` (2-D Gaussian map) and `time_resolved` (global joint fit) fields; their showcase panels are deferred — not rendered in "
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-2]]
- On constraint: false
- Location: `python/oracles/bench_contract.py:506`
- Finding domain: docs-drift
- Suggested fix / explanation: Two-fold drift: (1) the contract field is named `global_fit`, not `time_resolved` (it was renamed timeResolved->globalFit at SCHEMA_VERSION 1.5->1.6 per DECISIONS.md:6848); (2) both showcase panels ARE now registered and rendered in the Evidence dest
- Resolved by: [[evidence/phase-2-06-07-08-ev1]]
- Proposal: Removed LIMITATIONS.md's stale 'Dashboard showcase (deferred)' section — both showcases are now rendered. Strategy: e, Tier 3. Blast radius: local+reversible.
