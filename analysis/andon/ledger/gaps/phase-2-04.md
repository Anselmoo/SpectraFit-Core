---
type: gap
title: "[High] docs-drift: The Arctan/Tanh/Erfc step catalog spells the params step_height/step_center/step_width; these map to amplitude/center/si"
description: "python/oracles/cases.py:246 — The Arctan/Tanh/Erfc step catalog spells the params step_height/step_center/step_width; these map to amplitude/center/sigma and are exposed as recoverable bg.* true params (see spectrum_schema._backgr"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-2]]
- On constraint: false
- Location: `python/oracles/cases.py:246`
- Finding domain: docs-drift
- Suggested fix / explanation: Neither the step_height/step_center/step_width parameter aliases nor the spectrum_schema module/_background_true_params function exist in the current codebase; StepSpec uses amplitude/center/sigma directly with no renaming layer.
- Resolved by: [[evidence/phase-2-04-ev1]]
- Proposal: Corrected MODELS.md's step-param claim: StepSpec uses amplitude/center/sigma directly, no step_height/step_center/step_width alias, no spectrum_schema module. Strategy: e, Tier 3. Blast radius: local+reversible.
