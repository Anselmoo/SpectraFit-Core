---
type: gap
title: "[Medium] code-idiom: long-function"
description: "crates/spectrafit-levenberg-marquardt/src/driver.rs:161 — long-function"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-3]]
- On constraint: true
- Location: `crates/spectrafit-levenberg-marquardt/src/driver.rs:161`
- Finding domain: code-idiom
- Suggested fix / explanation: Extract cohesive sub-steps (e.g. Moré diag update, the inner lambda-search loop, the accept/reject + gain-ratio block) into private helper functions/methods so each concern can be unit-tested and read independently of the outer control flow.
- Resolved by: [[evidence/phase-3-01-ev1]]
- Proposal: Extracted 3 self-contained pure blocks from minimize() into named functions preceding it: update_more_scaling (Moré column-scaling diagonal update), compute_gradient_and_optimality (gradient/gnorm/opt_norm/trust_scaling, returning trust_v to avoid a second trust_scaling call), compute_step_diag (Coleman-Li step-diagonal fold). Deliberately left the report!/bump_lambda! local macros and the inner lambda-search + gain-ratio/accept-reject loop untouched inline in minimize() — the file's own comments document why those must stay local macros (macro hygiene + shared mutable state + early return from the enclosing function), matching the conservative precedent of gap 2-12 (deliberate no-change on tightly-coupled state) applied to only the safely-separable portion of this function. Strategy: a. Blast radius: local+reversible.
