---
type: gap
title: "[High] docs-drift: An inferential hypothesis test behind the headline... The only inferential tests today — accuracy-parity equivalence (TO"
description: "python/oracles/audit/wires.py:586 — An inferential hypothesis test behind the headline... The only inferential tests today — accuracy-parity equivalence (TOST, FDR-controlled) and bootstrap winner-stability — are scoped to per-case accu"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-2]]
- On constraint: false
- Location: `python/oracles/audit/wires.py:586`
- Finding domain: docs-drift
- Suggested fix / explanation: Wires W10 (σ-calibration, a CI-inclusion TOST on parameter-uncertainty pull coverage) and W11 (speed-significance) are additional gate-affecting inferential tests beyond the two the doc names, added via commit 3b2d9dd ('feat(audit): W10 σ-calibration
- Resolved by: [[evidence/phase-2-06-07-08-ev1]]
- Proposal: Updated LIMITATIONS.md's inferential-tests list to include W10 (sigma-calibration) and W11 (speed-inference) alongside the two originally named. Strategy: e, Tier 3. Blast radius: local+reversible.
