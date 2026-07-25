---
type: gap
title: "[High] docs-drift: bounds-enforcement-mechanism drift"
description: "crates/spectrafit-solver/src/problem.rs:129 — Bounds (min, max) are enforced by clamping inside residuals()."
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-5]]
- On constraint: true
- Location: `crates/spectrafit-solver/src/problem.rs:129`
- Finding domain: docs-drift
- Suggested fix / explanation: Verify the actual bounds-enforcement mechanism against the code at
  problem.rs:129 and correct whichever side (the claimed doc text, or a stale comment) has
  drifted.
- Resolved by: [[evidence/phase-5-01-ev1]]
- Proposal: The claim ("clamping inside residuals()") is stale — traced to ARCHITECTURE.md:200,
  not problem.rs:129 itself (that docstring already correctly describes reflective bounds
  projection). Confirmed via `LmProblem::apply_free_params` (problem.rs:143-158) and
  `reflect_into_bounds` (problem.rs:510-528): bounds are enforced by REFLECTION (mirroring an
  overshoot back into range, parking at the bound on extreme overshoot), not clamping, and it
  runs in `apply_free_params`/`set_params`, not `residuals()`. Matches the Behavior Contract's own
  "Reflective bounds projection" P1 rule for this phase. Fixed ARCHITECTURE.md:200 to describe the
  actual mechanism and its real location. Strategy: e (structural/connectivity). Blast radius:
  local+reversible.
