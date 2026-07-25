---
type: gap
title: "[Low] arch-health: new dispatch<->postfit intra-crate module cycle from gap phase-5-02's refactor"
description: "crates/spectrafit-solver/src/postfit.rs imported dispatch::LmSolveOutcome, creating a bidirectional dispatch<->postfit module dependency, contradicting postfit.rs's own 'solver-agnostic, never depends on which strategy ran' doc comment"
tags: ["kind:bug", "status:closed", "domain:arch-health", "severity:low"]
timestamp: "2026-07-25T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `crates/spectrafit-solver/src/postfit.rs:19` (removed), `crates/spectrafit-solver/src/dispatch.rs:33,257`
- Finding domain: arch-health (discovered by a dedicated re-check agent, dispatched per the
  brief's own stated exit criteria: "re-run self-assess-arch-health after this phase's fixes land
  to confirm no new deficiency was introduced" — never actually done until now, at the user's
  request, after the full sweep completed)
- Suggested fix / explanation: the reviewer's own suggestion — "the fix would be to define
  LmSolveOutcome/PostfitInputs in a third sibling module (or in postfit.rs itself, with dispatch.rs
  importing it) rather than have postfit reach back into dispatch."
- Resolved by: [[evidence/unattributed-archhealth-ev1]]
- Proposal: Traced to gap phase-5-02 (this session's own earlier fix, Phase 5 of the brief):
  reducing `assemble_result`'s argument count reused the existing `dispatch::LmSolveOutcome`
  struct by having `postfit.rs` import it (`use crate::dispatch::LmSolveOutcome;`), creating a
  NEW `postfit → dispatch` edge alongside the pre-existing `dispatch → postfit` edge (dispatch
  calls `postfit::assemble_result`) — a genuine bidirectional module dependency that didn't exist
  before that fix, below stage/crate granularity so it never showed up in the stage_graph.json
  check, but real and worth fixing given `postfit.rs`'s own module doc comment explicitly claims
  "solver-agnostic... never [depends] on which strategy ran," which `LmSolveOutcome` (a
  dispatch-owned, strategy-specific-shaped type) contradicted. Fixed by moving `LmSolveOutcome`'s
  definition INTO `postfit.rs` (its only real consumer — the outcome fields are destructured and
  threaded through `assemble_result`'s body) and having `dispatch.rs` import it from there
  instead (`use crate::postfit::{self, LmSolveOutcome};`), restoring the original one-directional
  `dispatch → postfit` dependency (matching the pre-phase-5-02 direction). Also lightly reworded
  `postfit.rs`'s module doc comment to clarify `LmSolveOutcome` is carried as opaque
  per-strategy-shaped data, not a discriminator the module's logic branches on — directly
  addressing the reviewer's cited contradiction. Verified: `cargo build -p spectrafit-solver`
  clean, `cargo clippy -p spectrafit-solver --all-targets -- -D warnings` clean, `cargo test -p
  spectrafit-solver` 51 unit + 1 gaussian2d + 9 parity passed (1 ignored timing test) — exact
  same shape as before the fix, confirming no behavior change (pure module-boundary reshuffle).
  Strategy: e (structural/connectivity — the actual finding was itself surfaced by a structural
  re-audit; the fix directly resolves the cited edge). Blast radius: local+reversible (both
  `LmSolveOutcome` and `PostfitInputs` remain crate-internal `pub` items with zero external
  consumers, confirmed via grep in the original phase-5-02 evidence).
