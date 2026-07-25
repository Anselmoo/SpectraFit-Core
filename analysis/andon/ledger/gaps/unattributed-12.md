---
type: gap
title: "[Medium] code-idiom: long-function-deep-nesting"
description: ".claude/validators/pydantic_create.py:134 — long-function-deep-nesting"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `.claude/validators/pydantic_create.py:134`
- Finding domain: code-idiom
- Suggested fix / explanation: Extract each file-type branch into its own small function and
  dispatch through a table/registry.
- Resolved by: [[evidence/unattributed-python-ev1]]
- Proposal: Same decomposition pattern as [[gaps/unattributed-11]] (the sibling `pydantic_edit.py`
  finding): `CreateValidation.validate_context_specific` (152 lines, 5 file-type branches) split
  into 5 private methods (`_validate_python_file`, `_validate_rust_file`,
  `_validate_markdown_file`, `_validate_results_index`, `_validate_results_feedback`), moved
  verbatim; the shared prelude (parent-dir-creatable check, file-already-exists check) stays
  inline in the dispatcher since it's not branch-specific. Used a plain `if`/`elif` dispatcher
  (not a table/registry) matching the sibling fix's reasoning — `.endswith()` checks, not an `==`
  chain, so a dict-dispatch table would need its own key-matching logic reimplemented anyway for
  no real simplicity gain over 5 `elif` lines. Functionally tested 14 scenarios (python/rust/
  markdown pass+fail cases, results_index.json 2 sub-cases, results_feedback.json 2 sub-cases,
  file-already-exists, path traversal, unrelated extension) via direct CLI invocation in an
  isolated temp directory — byte-identical output between original (`git show HEAD:...`) and
  refactored versions across all 14. `uv run ruff check` reports the same 13 pre-existing warnings
  on both versions; `uv run ty check` passes clean. Strategy: a (functional equivalence across all
  branches). Blast radius: local+reversible.
