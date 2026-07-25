---
type: gap
title: "[Low] code-idiom: long-function"
description: "crates/spectrafit-graph/src/compiler.rs:120 — long-function"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-3]]
- On constraint: false
- Location: `crates/spectrafit-graph/src/compiler.rs:120`
- Finding domain: code-idiom
- Suggested fix / explanation: Split into private associated functions per numbered step (e.g. `reject_duplicate_ids`, `build_free_keys`, `build_node_free_cols`) called in sequence from `compile()`, keeping the top-level function as an orchestrator.
- Resolved by: [[evidence/phase-3-03-ev1]]
- Proposal: compile() (158 lines, 5 sequential steps) decomposed into 5 private standalone functions (reject_duplicate_ids, collect_tied_targets, compile_nodes, build_free_keys, build_node_free_cols) inserted before impl CompiledGraph; compile() itself is now a 9-line orchestrator calling them in original order with state threaded via parameters/return values instead of shared locals. Strategy: a. Blast radius: local+reversible.
