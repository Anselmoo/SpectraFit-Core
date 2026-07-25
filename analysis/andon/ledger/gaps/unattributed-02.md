---
type: gap
title: "[High] ci-topology: ci.yml lint:rust missing cargo-fmt parity"
description: ".github/workflows/ci.yml:66 — ci.yml lint:rust step claims EXACT parity with GitLab's lint:rust but omits the cargo fmt check"
tags: ["kind:bug", "status:closed", "domain:ci-topology", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: true
- Location: `.github/workflows/ci.yml:66`
- Finding domain: ci-topology
- Suggested fix / explanation: Add `rustup component add rustfmt` + `cargo fmt --all -- --check`
  to the GitHub lint:rust step to match `.gitlab/20-lint.yml`'s `lint:rust` job.
- Resolved by: [[evidence/unattributed-ci-ev1]]
- Proposal: Confirmed real via direct inspection: the "Lint Rust" step's comment claims "Mirrors
  .gitlab/20-lint.yml lint:rust EXACTLY" but only ran `cargo clippy`, missing `cargo fmt --all --
  --check` (which `.gitlab/20-lint.yml` has, added after ~40 files of rustfmt drift accumulated
  undetected, per its own comment). Added the missing steps (rustfmt component + fmt check).
  Running the new check locally surfaced a REAL, currently-existing formatting drift in
  `crates/spectrafit-graph/src/compiler.rs` (introduced by this session's own Phase 3 refactor,
  gap 3-03) — fixed via `cargo fmt --all`, re-verified `cargo fmt --all -- --check` clean, and
  re-ran `cargo build -p spectrafit-graph` + `cargo test -p spectrafit-graph` (50/50 passed) to
  confirm the formatting-only change didn't alter behavior. Also independently re-ran
  `cargo clippy --workspace --all-targets -- -D warnings` (MEM_GUARD_OFF=1, full workspace) to
  confirm the new gate's other half stays green too. Strategy: e (structural/connectivity).
  Blast radius: local+reversible.
  CORRECTION (caught by the independent verifier): I told the verification agent to check
  `git diff HEAD -- crates/spectrafit-graph/src/compiler.rs` and described it as "whitespace-only
  / a single line's wrapping changed" — that was imprecise. `git diff HEAD` shows everything
  uncommitted since HEAD, which includes gap 3-03's full 5-function extraction from earlier in
  this session (already independently verified separately, see phase-3-03-ev1.md), not just this
  gap's own incremental fmt fix. The fmt fix itself IS whitespace-only (one line's wrapping,
  confirmed via `cargo fmt --all` producing exactly that one change); the cumulative diff-vs-HEAD
  is not, and I described the wrong scope. The verifier independently re-confirmed the *whole*
  compiler.rs diff (both the earlier refactor and this fmt fix) is logic-preserving regardless
  (line-for-line identical extracted-function bodies, 50/50 tests green) — a welcome bonus
  double-check, but the lesson is to scope verification instructions to the actual delta being
  claimed, not a blanket `diff HEAD`.
