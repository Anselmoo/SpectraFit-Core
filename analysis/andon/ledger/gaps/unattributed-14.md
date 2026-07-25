---
type: gap
title: "[Low] lint-audit: canonical-wire-format-method"
description: "python/oracles/MODELS_CATALOG.md:16 — canonical-wire-format-method: exactly one canonical wire-format string per model, produced by ModelTypeStr::as_str()"
tags: ["kind:bug", "status:closed", "domain:lint-audit", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `python/oracles/MODELS_CATALOG.md:16`
- Finding domain: lint-audit
- Suggested fix / explanation: The kernel-addition path description names a deprecated
  duplicated-per-crate `model_type_to_str` architecture instead of the current canonical
  `ModelTypeStr::as_str()` single source of truth.
- Resolved by: [[evidence/unattributed-docs-ev1]]
- Proposal: CLAUDE.md's own "Adding a New Benchmark Model" section (already accurate, unaffected
  by this fix) documents the real current architecture: the Rust↔Python `ModelType` string was
  collapsed from per-crate duplicate tables into one canonical match arm on
  `ModelTypeStr::as_str()` in `spectrafit-types`, read by `spectrafit-graph::compiler` and
  `spectrafit-varpro`. MODELS_CATALOG.md:16 still described the old "→ `model_type_to_str` in
  both spectrafit-graph and spectrafit-varpro" duplicated-table path. Rewrote the sentence to
  match CLAUDE.md's accurate description, and updated the parallelization note (which listed the
  old "two model_type_to_str tables" as one of the serializing shared files) to instead name
  `ModelTypeStr::as_str()`'s match arm and the `spectrafit-builder` exhaustiveness gate — the
  actual current set of shared registration files a new kernel touches, per CLAUDE.md's own
  "Adding a New Benchmark Model" step 2. Docs-only change, cross-checked against CLAUDE.md
  (already-accurate reference) rather than re-deriving from source. Strategy: e
  (structural/connectivity). Blast radius: local+reversible.
