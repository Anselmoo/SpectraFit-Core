---
type: evidence
title: "LIMITATIONS.md spc-bench claim correction is accurate"
description: "Independent verification confirms spc-bench genuinely has no console-script entry (pyproject.toml parsed live, regression-guard tests present), the Option A removal rationale matches CLAUDE.md and the test file's own docstring verbatim, and the fix was correctly scoped to only the spc-bench clause (PyO3 ABI / BenchReport contract claims untouched). CORRECTION (2026-07-24, unattributed-05 pass): the '2026-06-20' date this verification certified as cross-doc-consistent was itself wrong on all sides — real git log ground truth is 2026-06-23 (commit f1e8c06). This evidence doc checked internal consistency (docs agree with each other) but never checked against git log, so a repo-wide wrong date got certified as verified; see DECISIONS.md/CLAUDE.md/CONTRIBUTING.md/LIMITATIONS.md/the test docstring, all corrected in the same pass."
resource: "LIMITATIONS.md"
tags: ["strategy:e", "tier:3"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gap phase-4-01 (docs, phase-4/tests) — the finding's cited location
  (tests/meta/test_console_scripts.py:30) actually asserts the OPPOSITE of the drifted claim (a
  regression guard confirming spc-bench does NOT exist), which is what flagged LIMITATIONS.md's
  Status section as drifted from the real code state.
- Verdict: green
- Strategy detail: e (structural/connectivity — docs claim vs. actual repo state), Tier 3
  (independent agent re-derivation: live tomllib parse of pyproject.toml, direct read of the
  regression-guard tests, direct read of CLAUDE.md). Confirmed `'scripts' in
  pyproject.toml['project']` is False and no `spc-bench` string appears anywhere in pyproject.toml;
  confirmed `test_no_spc_bench_console_script_published` and
  `test_pyproject_declares_no_project_scripts` exist as described; confirmed CLAUDE.md
  independently states the identical "Option A packaging, 2026-06-20" removal rationale and the
  `uv run poe benchmark` / `python -m oracles.cli` replacement commands, verbatim-matching the new
  LIMITATIONS.md text. Confirmed the fix is narrowly scoped — PyO3 ABI / BenchReport contract
  "not yet stable" claims and the DECISIONS.md cross-reference were left untouched, only the
  spc-bench clause changed.
- Non-overridable: false
