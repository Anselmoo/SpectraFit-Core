---
type: gap
title: "[High] docs-drift: spc-bench removal date wrong repo-wide (2026-06-20 vs actual 2026-06-23)"
description: "CLAUDE.md, LIMITATIONS.md, CONTRIBUTING.md, tests/meta/test_console_scripts.py docstring, docs/whitepaper_methodology.md, and 2 ledger records all cite 2026-06-20; the actual commit (f1e8c06) is dated 2026-06-23"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: true
- Location: `CLAUDE.md` (2 occurrences), `LIMITATIONS.md:65`, `CONTRIBUTING.md:51`,
  `tests/meta/test_console_scripts.py:4` (the actual root source — a docstring, not a doc file),
  `docs/whitepaper_methodology.md`, `analysis/andon/ledger/evidence/phase-4-01-ev1.md`,
  `analysis/andon/ledger/gaps/phase-4-01.md`
- Finding domain: docs-drift
- Suggested fix / explanation: `git log --format='%h %ad %s' --date=short` shows commit `f1e8c06`
  ("fix(packaging): lean wheel — drop spc-bench console script...") dated 2026-06-23, contradicting
  every doc's "2026-06-20" claim. `2026-06-20` doesn't correspond to any spc-bench-related commit
  at all — it's simply the wrong date, propagated from a single wrong source.
- Resolved by: [[evidence/unattributed-methodology-ev1]]
- Proposal: Traced the wrong date to its actual root: `tests/meta/test_console_scripts.py`'s own
  module docstring ("Packaging decision (Option A, 2026-06-20)") — every doc that got this wrong
  was citing that test file as its source of truth, so the error propagated from ONE place, not
  independently. Fixed the docstring first (verified `uv run pytest tests/meta/
  test_console_scripts.py` still passes — docstring-only change), then fixed every downstream
  citation: CLAUDE.md (2 occurrences, `sed` global replace), LIMITATIONS.md:65,
  CONTRIBUTING.md:51, `docs/whitepaper_methodology.md` (same batch as the python/benchmark→
  python/oracles rename in [[unattributed-16]]'s companion fix). Also corrected 2 of THIS
  session's own earlier ledger records (`gaps/phase-4-01.md`, `evidence/phase-4-01-ev1.md`) that
  had certified "2026-06-20" as verified during Phase 4 — that verification checked cross-doc
  consistency (docs agreeing with each other) but never checked against `git log` itself, so a
  repo-wide wrong date got certified as green. Per this ledger's own append-only discipline
  (matching DECISIONS.md's convention), added correction notes to those 2 records rather than
  silently rewriting their historical Proposal text. Strategy: b (oracle-gap — `git log` is
  external ground truth) for the date itself; e for the propagation trace. Blast radius:
  local+reversible.
  Post-verification addendum: the independent verifier found one instance this pass missed —
  `tests/meta/test_wheel_scope.py:26` carried the same stale "2026-06-20" in an "Option A
  packaging decision" assertion string. Fixed and re-verified (`uv run pytest
  tests/meta/test_wheel_scope.py -q` → 1 passed).
