---
type: evidence
title: "dispatch<->postfit module cycle fix verified — one-directional dependency restored"
description: "Independent verification confirms LmSolveOutcome's full definition (all 8 fields, types, docs) moved intact from dispatch.rs to postfit.rs, postfit.rs has zero use crate::dispatch::... imports, dispatch.rs imports LmSolveOutcome from postfit (one-directional dependency), both call sites still type-check, build/clippy/test all clean with identical test counts (51+1+9), no stray dispatch::LmSolveOutcome references remain anywhere in crates/, and the updated module doc's claim (LmSolveOutcome is carried as opaque data, never inspected/branched-on) is true — confirmed no .is_empty()/match/if on the history fields anywhere in postfit.rs."
resource: "crates/spectrafit-solver/src/dispatch.rs, crates/spectrafit-solver/src/postfit.rs"
tags: ["strategy:e", "tier:1"]
timestamp: "2026-07-25T00:00:00Z"
---

## Evidence detail

- Wire: gap unattributed-24
- Verdict: green
- Strategy detail: e (structural/connectivity — the finding itself was a structural
  re-audit result; verification directly re-confirms the edge direction). Independent reviewer
  read the diff, confirmed the struct's 8 fields/types/docs moved intact (enriched with per-field
  docs, nothing dropped), confirmed `postfit.rs` has exactly one `use crate::` line
  (`crate::problem::LmProblem`) and zero `dispatch` imports, confirmed `dispatch.rs`'s only
  `postfit`-related import is `use crate::postfit::{self, LmSolveOutcome};`, confirmed both call
  sites (`run_lm_solve`'s construction, `fit()`'s consumption) type-check, independently ran
  `cargo build`/`clippy -D warnings`/`test` for spectrafit-solver (all clean, forced a real
  recompile via touch to rule out a stale-cache pass) with identical 51+1+9 test counts to before
  the fix, grepped the whole `crates/` tree for stray `dispatch::LmSolveOutcome` references (none
  found), and read the module body to confirm the trajectory-history fields are only ever moved
  through to the final `FitResultSpec`, never inspected/branched-on — validating the updated
  module doc's own claim. One observation noted (not a defect): the diff-vs-HEAD also contains an
  earlier, already-verified, unrelated comment expansion in the same file
  (`apply_postfit_guards`'s amplitude-semantics rationale, from gap phase-5-03/04) — expected
  since `git diff HEAD` is cumulative across the whole session, not scoped to this one fix.
- Non-overridable: false
