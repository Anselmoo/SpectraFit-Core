---
type: gap
title: "[Medium] code-idiom: too-many-arguments-blanket-allow"
description: "crates/spectrafit-solver/src/postfit.rs:29 — too-many-arguments-blanket-allow (Group the related inputs into a small context/params struct, e.g. a PostfitInputs { cg, graph, datasets, x_all, y_all, ... })"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-5]]
- On constraint: false
- Location: `crates/spectrafit-solver/src/postfit.rs:29`
- Finding domain: code-idiom
- Suggested fix / explanation: Group the related inputs into a small context/params struct (e.g.
  a `PostfitInputs { cg, graph, datasets, x_all, y_all, ... }`).
- Resolved by: [[evidence/phase-5-02-ev1]]
- Proposal: `assemble_result` (single call site: dispatch.rs) took 13 positional args. Added
  `pub struct PostfitInputs<'a> { cg, graph, datasets, x_all, y_all }` in postfit.rs for the
  read-only graph/data context (per the finding's own suggested shape). The remaining 8 args
  (result_problem + 7 solve-outcome scalars/histories) exactly matched an existing struct,
  `dispatch::LmSolveOutcome` (already constructed at the one call site right before this call) —
  bumped its visibility to `pub` (with doc comments, satisfying `#![warn(missing_docs)]`) and
  changed `assemble_result` to take it by value instead of destructuring+repacking 8 of its own
  fields as separate params. New signature: `assemble_result(outcome: LmSolveOutcome<'_>, inputs:
  PostfitInputs<'_>, init_fit: Vec<f64>)` — 3 params, no `#[allow(clippy::too_many_arguments)]`
  needed (removed, confirmed clean under `-D warnings`). Strategy: a. Blast radius:
  local+reversible (single call site, same crate, no external consumer of `assemble_result` or
  `LmSolveOutcome` — verified via grep).
