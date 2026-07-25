---
type: gap
title: "[High] docs-drift: enforce-pydantic-native hook claim (VERIFIED ACCURATE)"
description: ".claude/hooks/enforce-pydantic-native.sh:79 — This codebase is Pydantic-first — the enforce-pydantic-native hook is not a suggestion"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `.claude/hooks/enforce-pydantic-native.sh:79`
- Finding domain: docs-drift
- Suggested fix / explanation: verify the hook still enforces what it claims to.
- Resolved by: [[evidence/unattributed-methodology-ev1]]
- Proposal: **No change — claim verified accurate.** Confirmed the hook still blocks
  (`SystemExit(2)`, stderr) three violation classes in proposed `.py` edits under
  `python/oracles/`/`tests/`: dict-indexing instead of typed attribute access,
  `run_quick_validation_case(` calls without `QuickValidationRunPayload` typing, and
  `json.loads(...)` combined with dict-indexing instead of Pydantic validation. Confirmed it's
  wired twice in `.claude/settings.json` (PreToolUse matchers for both `Edit` and `Write`), both
  blocking, not warn-only. "Not a suggestion" remains true. No fix needed. Strategy: e
  (structural/connectivity). Blast radius: none (no change made).
