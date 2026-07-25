---
type: gap
title: "[High] confab:contract-drift: TypeSignature"
description: "python/spectrafit_core/models.py:77 — TypeSignature"
tags: ["kind:bug", "status:closed", "domain:confab:contract-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `python/spectrafit_core/models.py:77`
- Finding domain: confab:contract-drift
- Suggested fix / explanation: ModelNodeSpec.dataset_index: int | None = None — Python type hint places no lower bound, so any int (including negative) type-checks.
- Resolved by: [[evidence/phase-1-06-ev1]]
- Proposal: Added a Pydantic field_validator on ModelNodeSpec.dataset_index rejecting negative values, closing the Python int|None vs Rust Option<usize> contract gap. Strategy: f (property/invariant). Blast radius: local+reversible.
