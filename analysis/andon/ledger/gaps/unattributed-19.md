---
type: gap
title: "[High] docs-drift: LIMITATIONS.md claims alpha, project is beta"
description: "LIMITATIONS.md:3 — spectrafit-core is alpha software; :61-62 says APIs are unstable 'before the beta release', implying beta hasn't happened"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: true
- Location: `LIMITATIONS.md:3`, `LIMITATIONS.md:61-62`
- Finding domain: docs-drift
- Suggested fix / explanation: pyproject.toml/CHANGELOG.md/README.md all say the project was
  promoted to beta (0.1.0b1) 2026-06-23; LIMITATIONS.md is the one doc still saying alpha.
- Resolved by: [[evidence/unattributed-methodology-ev1]]
- Proposal: Confirmed ground truth: `pyproject.toml` version `0.1.0b1`, classifier
  `Development Status :: 4 - Beta`; `CHANGELOG.md`'s `[0.1.0b1] - 2026-06-23` entry: "Promoted to
  **beta**"; `README.md` already correctly says beta; a regression-guard test
  (`tests/meta/test_version_beta.py`) already pins version==0.1.0b1 and the Beta classifier.
  Fixed LIMITATIONS.md:3 (alpha → beta, with the promotion date) and :61-62 (dropped the "before
  the beta release" phrasing implying beta is a future milestone — beta was reached over a month
  ago; reworded to "may still occur post-beta, before a 1.0 release"). Also fixed the same
  paragraph's stale spc-bench removal date (2026-06-20 → 2026-06-23) in the same edit — see
  [[unattributed-20]]. Strategy: e (structural/connectivity — pyproject.toml/CHANGELOG.md/
  README.md/existing regression test all independently agree on beta). Blast radius:
  local+reversible.
