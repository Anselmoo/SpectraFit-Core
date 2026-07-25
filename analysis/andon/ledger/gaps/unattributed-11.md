---
type: gap
title: "[Medium] code-idiom: long-function-deep-nesting"
description: ".claude/validators/pydantic_edit.py:116 — long-function-deep-nesting"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `.claude/validators/pydantic_edit.py:116`
- Finding domain: code-idiom
- Suggested fix / explanation: Split into one small validator function per file-type branch
  (Rust PyO3, Cargo.toml, Python schema, results_index.json, results_feedback.json).
- Resolved by: [[evidence/unattributed-python-ev1]]
- Proposal: `EditValidation.validate_context_specific` (148 lines, 5 file-type branches) split into
  5 private methods (`_validate_rust_pyfunction`, `_validate_cargo_toml`,
  `_validate_python_schema`, `_validate_results_index`, `_validate_results_feedback`), each moved
  verbatim (same logic, same return values), with `validate_context_specific` now a short
  dispatcher (`if`/`elif` on `.endswith()`/`in` string checks — not an `==` chain on one variable,
  so the project's `enforce-match-dispatch` house rule doesn't apply here even where it would be
  in scope). Functionally tested all 5 branches plus edge cases (12 scenarios: rust pyfunction
  pass/violation, Cargo.toml, python schema pass/violation, results_index.json 3 sub-cases,
  results_feedback.json 3 sub-cases, path traversal, unrelated file) via direct CLI invocation
  (`uv run python ... <path> <content>`) comparing original (`git show HEAD:...`) vs refactored —
  byte-identical JSON output across all 12. `uv run ruff check` reports the same 12 pre-existing
  D415 (docstring punctuation) warnings on both versions — no new lint issues introduced;
  `uv run ty check` passes clean on both. Strategy: a (functional equivalence across all
  branches). Blast radius: local+reversible.
