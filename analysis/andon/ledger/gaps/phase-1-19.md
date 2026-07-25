---
type: gap
title: "[Low] code-idiom: dead-variable"
description: ".claude/hooks/lib/git-hygiene.sh:165 — dead-variable"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `.claude/hooks/lib/git-hygiene.sh:165`
- Finding domain: code-idiom
- Suggested fix / explanation: Either use `$pruned_count` in the final summary echo (e.g. report whether a prune actually removed stale registrations) or delete the dead assignment.
- Resolved by: [[evidence/phase-1-shell-ev1]]
- Proposal: git-hygiene.sh's pruned_count is now read in the summary echo (prune_note), no longer a dead write-only variable. Strategy: a. Blast radius: local+reversible.
