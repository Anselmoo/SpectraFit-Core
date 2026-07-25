---
type: gap
title: "[High] ci-topology: ci.yml lint:python missing ruff-format parity"
description: ".github/workflows/ci.yml:60 — ci.yml lint job claims exact parity with GitLab's lint:python but is missing the ruff-format check"
tags: ["kind:bug", "status:closed", "domain:ci-topology", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: true
- Location: `.github/workflows/ci.yml:60`
- Finding domain: ci-topology
- Suggested fix / explanation: Add `ruff format --check` to the GitHub lint job to match
  `.gitlab/20-lint.yml`'s `lint:python` job.
- Resolved by: [[evidence/unattributed-ci-ev1]]
- Proposal: Confirmed real via direct inspection: `.github/workflows/ci.yml`'s lint job comment
  claims "Mirrors .gitlab/20-lint.yml lint:python" but only ran `ruff check` + `ty check`,
  missing `ruff format --check` (which `.gitlab/20-lint.yml` has, added after a real 120-file
  formatting-drift incident per its own comment). Added the missing step. Verified locally before
  landing: `uv run ruff format --check .` passes clean on the current tree (272 files already
  formatted) — the new gate would not have broken the pipeline. Strategy: e
  (structural/connectivity — CI config claim vs. actual steps). Blast radius: local+reversible
  (adds a check to a non-blocking-yet lint job; verified it currently passes).
