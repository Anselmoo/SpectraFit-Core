---
type: evidence
title: "SHAPE_BOUNDS registry consolidation is complete and correct"
description: "Independent verification confirms the shared table, both backend imports, full repo-wide absence of stale references, and both test files updated consistently — including a genuinely strengthened identity-based parity test."
resource: "python/oracles/models.py"
tags: ["strategy:a", "tier:1"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gap phase-2-10 (code, phase-2/oracles)
- Verdict: green
- Strategy detail: a (independent reviewer, Rung 1-2) — confirmed SHAPE_BOUNDS defined once in
  oracles/models.py with identical values to both prior copies; both backends import it with old
  locals fully removed; repo-wide grep found zero stale live-code/live-doc references (only
  expected DECISIONS.md historical mentions); both test files updated, with the parity test
  genuinely strengthened from value-equality to object-identity. Ran the actual tests (not just
  read them) — 2 + 9 passing.
- Non-overridable: false
