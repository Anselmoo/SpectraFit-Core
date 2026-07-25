---
type: evidence
title: "assemble_result argument-count refactor is correct and behavior-preserving"
description: "Independent verification confirms assemble_result now takes 3 params (outcome/inputs/init_fit), the too-many-arguments allow is gone with no warning reintroduced, the single call site was updated correctly, no other repo file references the changed items, and build/clippy(-D warnings)/test are green for spectrafit-solver plus the full workspace."
resource: "crates/spectrafit-solver/src/postfit.rs"
tags: ["strategy:a", "tier:1"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gap phase-5-02 (code, phase-5/spectrafit-solver)
- Verdict: green
- Strategy detail: a (independent reviewer, Rung 2) — confirmed assemble_result's new 3-param
  signature (outcome: LmSolveOutcome<'_>, inputs: PostfitInputs<'_>, init_fit: Vec<f64>), the
  removed #[allow(clippy::too_many_arguments)] (only two other, unrelated functions in the file
  still carry it), LmSolveOutcome's pub fields with doc comments (satisfying
  #![warn(missing_docs)]), PostfitInputs's 5 documented fields, and the dispatch.rs call site
  updated to pass outcome directly + a PostfitInputs literal instead of destructuring 8 loose
  locals. Repo-wide grep confirmed no other .rs/.py file references assemble_result/
  LmSolveOutcome/PostfitInputs. Independently ran (forced rebuild via touch first): `cargo build
  -p spectrafit-solver` clean; `cargo clippy -p spectrafit-solver --all-targets -- -D warnings`
  0 warnings; `cargo test -p spectrafit-solver` 51 unit + 1 gaussian2d + 9 parity passed, 1
  ignored timing test — exact expected shape; `cargo build --workspace --lib` clean including the
  PyO3 binding crate spectrafit-core, confirming the LmSolveOutcome visibility bump didn't break
  anything workspace-wide.
- Non-overridable: false
