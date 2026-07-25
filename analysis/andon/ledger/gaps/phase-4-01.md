---
type: gap
title: "[High] docs-drift: stability-claim drift"
description: "tests/meta/test_console_scripts.py:30 — APIs (PyO3 ABI, the BenchReport contract, the spc-bench CLI) are not yet stable; breaking change"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-4]]
- On constraint: true
- Location: `tests/meta/test_console_scripts.py:30`
- Finding domain: docs-drift
- Suggested fix / explanation: The test/doc claims PyO3 ABI, the `BenchReport` contract, and the
  `spc-bench` CLI are stable APIs guarded against breaking changes. This is stale: `spc-bench` the
  console-script entry point was removed (Option A packaging, 2026-06-20) — CLAUDE.md documents
  this explicitly ("The `spc-bench` console script was removed... run the bench via `uv run poe
  benchmark` or `uv run python -m oracles.cli`"). Verify the actual current claim/assertion in the
  test against present reality and correct whichever side (test assertion text, or a stale
  docstring/comment) has drifted.
- Resolved by: [[evidence/phase-4-01-ev1]]
- Proposal: The finding's evidence text traces to LIMITATIONS.md:61 ("Status" section), not the
  cited tests/meta/test_console_scripts.py:30 itself — that test file actually asserts the
  OPPOSITE (a regression guard confirming spc-bench does NOT exist), which is what flagged the
  doc as drifted. Fixed LIMITATIONS.md:61 to drop the stale "spc-bench CLI... not yet stable"
  claim (spc-bench was fully removed, Option A packaging, 2026-06-20 — not merely unstable) and
  added the correct current invocation surface (uv run poe benchmark / python -m oracles.cli),
  matching CLAUDE.md's own documented language for the same fact. Left the PyO3 ABI / BenchReport
  contract "not yet stable" claims untouched (out of scope for this finding, no evidence they are
  wrong). Strategy: e (structural/connectivity — docs claim vs. actual code state). Blast radius:
  local+reversible.
- CORRECTION (2026-07-24, unattributed-05 pass): the "2026-06-20" date cited above (twice) and
  certified as verified in [[evidence/phase-4-01-ev1]] was itself wrong — `git log` ground truth
  for the actual spc-bench removal commit (f1e8c06) is 2026-06-23. The original verification only
  checked cross-doc consistency (this doc agreeing with CLAUDE.md), never git log itself, so the
  wrong date propagated as "verified." Corrected everywhere it appeared (CLAUDE.md,
  CONTRIBUTING.md, LIMITATIONS.md, the test file's own docstring, and this doc's evidence
  description) in the same unattributed-pass batch.
