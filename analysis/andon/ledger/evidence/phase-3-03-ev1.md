---
type: evidence
title: "compiler.rs CompiledGraph::compile() decomposition is behavior-preserving"
description: "Independent verification confirms the 5-function extraction is a clean, behavior-preserving refactor: line-by-line diff trace, both safety-critical .unwrap() invariant comments correctly re-scoped, build/clippy/test green for spectrafit-graph and downstream spectrafit-solver."
resource: "crates/spectrafit-graph/src/compiler.rs"
tags: ["strategy:a", "tier:1"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gap phase-3-03 (code, phase-3/spectrafit-graph)
- Verdict: green
- Strategy detail: a (independent reviewer, Rung 2) — diffed against real HEAD via
  `git diff HEAD -- crates/spectrafit-graph/src/compiler.rs`, traced each of the 5 extracted
  functions (reject_duplicate_ids, collect_tied_targets, compile_nodes, build_free_keys,
  build_node_free_cols) line-by-line against the original inline steps, confirmed identical
  call order in the new compile() body and correct threading of tied_targets as a parameter.
  Both `.unwrap()` invariant comments (Jacobian column-layout safety arguments) were checked
  specifically: preserved and correctly re-worded for the new function boundaries, not weakened.
  One harmless note: build_node_free_cols rebuilds node_idx_by_id (a small redundant recompute
  vs. the original single build reused across steps), not a behavior change. Independently ran
  (not trusted from a prior run): `cargo build -p spectrafit-graph` (forced rebuild via touch),
  `cargo clippy -p spectrafit-graph --all-targets -- -D warnings` (clean), `cargo test -p
  spectrafit-graph` (50/50 passed), `cargo test -p spectrafit-solver` (downstream consumer —
  51 unit + 1 gaussian2d + 9 parity passed, 1 ignored timing test).
- Non-overridable: false
