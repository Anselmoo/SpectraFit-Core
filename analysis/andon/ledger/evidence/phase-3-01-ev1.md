---
type: evidence
title: "driver.rs minimize() partial decomposition is behavior-preserving"
description: "Independent verification confirms the 3-function extraction (Moré scaling update, gradient+optimality, step-diag) is byte-for-byte faithful, trust_scaling is still called exactly once per outer iteration (the specifically-flagged risk), the macro-based inner lambda-search loop is untouched, and build/clippy/test are green for both spectrafit-levenberg-marquardt and downstream spectrafit-solver."
resource: "crates/spectrafit-levenberg-marquardt/src/driver.rs"
tags: ["strategy:a", "tier:1"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gap phase-3-01 (code, phase-3/spectrafit-levenberg-marquardt) — highest-risk item in
  Phase 3 (core numerical solver, on_constraint: true)
- Verdict: green
- Strategy detail: a (independent reviewer, Rung 2) — diffed against real HEAD via
  `git diff HEAD -- crates/spectrafit-levenberg-marquardt/src/driver.rs`, traced all 3 extracted
  functions (update_more_scaling, compute_gradient_and_optimality, compute_step_diag) line by
  line against the removed inline blocks: identical arithmetic/conditionals/control-flow.
  Specifically checked (per explicit instruction, since this is the single highest numerical-risk
  point) that `problem.trust_scaling(&g_vec)` is still called exactly ONCE per outer iteration —
  confirmed: compute_gradient_and_optimality calls it once and returns trust_v as a 4th tuple
  element, which the caller passes by value into compute_step_diag rather than that function
  recomputing it; also reinforced by compute_gradient_and_optimality taking `problem: &P`
  (immutable), which the compiler enforces. Confirmed the trajectory-push
  (cost_history/gradient_norm_history/params_history) reordering relative to opt_norm computation
  is safe because trust_scaling takes &self and cannot mutate problem. Confirmed the report!/
  bump_lambda! local macros and the entire inner lambda-search + gain-ratio/accept-reject loop
  are byte-identical to pre-refactor and untouched by either diff hunk. Confirmed the `p =
  problem.n_params()` local remains live (used at 4 other call sites in minimize()) and clippy
  -D warnings passed clean (no unused-variable flag). Independently ran (not trusted from a
  prior run, file touched first to force rebuild): `cargo build -p
  spectrafit-levenberg-marquardt` clean; `cargo clippy -p spectrafit-levenberg-marquardt
  --all-targets -- -D warnings` clean; `cargo test -p spectrafit-levenberg-marquardt` 11/11
  passed; `cargo test -p spectrafit-solver` (downstream consumer) 51 unit + 1 gaussian2d + 9
  parity passed, 1 ignored timing spot-check — exact expected shape.
- Non-overridable: false
