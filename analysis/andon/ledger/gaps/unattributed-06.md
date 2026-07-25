---
type: gap
title: "[Low] code-idiom: unsafe-find-xargs-filename-splitting"
description: ".claude/hooks/pre-merge-pyO3.sh:26 — unsafe-find-xargs-filename-splitting"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `.claude/hooks/pre-merge-pyO3.sh:26`
- Finding domain: code-idiom
- Suggested fix / explanation: Use `find ... -print0 | xargs -0 grep -l ...` (or
  `find ... -exec grep -l {} +`) to make the pipeline safe for arbitrary filenames.
- Resolved by: [[evidence/unattributed-shell-ev1]]
- Proposal: Changed `find "$REPO_ROOT/crates" -name "*.rs" -type f | xargs grep -l "#\[pyfunction\]"`
  to `find "$REPO_ROOT/crates" -name "*.rs" -type f -exec grep -l "#\[pyfunction\]" {} +` (the
  `-exec ... +` form, no `-print0`/`xargs -0` pairing needed). Ran the fixed hook against the real
  repo (read-only, safe) — passes clean ("Checking 1 files... PASS"). Confirmed via git-stash
  A/B comparison that output is byte-identical to the original script on the real repo. Strategy:
  a (functional equivalence test). Blast radius: local+reversible (this hook is documented
  MANUAL-ONLY, not wired into any merge gate — audit F11, 2026-06-26 per the file's own header).
