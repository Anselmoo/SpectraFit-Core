---
type: gap
title: "[Low] code-idiom: long-function"
description: "python/oracles/audit/runner.py:82 — long-function"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-2]]
- On constraint: false
- Location: `python/oracles/audit/runner.py:82`
- Finding domain: code-idiom
- Suggested fix / explanation: Extract each documented sub-rule (core-wire cap, soft-cap wire cap, hard-cap wire cap, RUNG_5 unlock check) into its own small predicate function that `_compute_rung` composes.
- Proposal: RESOLVED AS NO-CHANGE after re-reading the function myself: _compute_rung's sub-rules are tightly interdependent (7+ shared local variables feed across the cascade: statuses, pass_count, unproven_count, base, w8/w10/w11_passed). Splitting into separate functions would mean threading that shared state through helper signatures rather than genuinely separating independent concerns — the function is exceptionally well-documented (27-line docstring explaining every rule) and has no deep nesting. Confirmed the earlier code-idiom verifier's own nuanced Low-severity downgrade and its explicit doubt that extraction would help. Declining to apply a mechanical extraction the evidence argues against; this is a deliberate won't-fix, not a skip.
