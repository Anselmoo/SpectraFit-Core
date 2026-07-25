---
type: gap
title: "[Medium] docs-drift: .toFixed() location claim (CLAUDE.md, devboard.md)"
description: "CLAUDE.md:423, .claude/skills/web-stream/references/devboard.md:36 — number formatting is not inline in web/src/panels/registry.tsx"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `CLAUDE.md:423`, `.claude/skills/web-stream/references/devboard.md:36`
- Finding domain: docs-drift
- Suggested fix / explanation: Number formatting — inline in `web/src/panels/registry.tsx`
  (`.toFixed()`).
- Resolved by: [[evidence/unattributed-methodology-ev1]]
- Proposal: `grep -n "toFixed" web/src/panels/registry.tsx` returns zero matches. Real current
  locations: `web/src/series/format.ts`'s `fmtP()` (a file added earlier this session, phase-1/2
  work), the `tickLabels` tick formatter in `web/src/series` (confirmed still exists at
  `web/src/series/index.ts`), and most panel bodies (`web/src/panels/bodies/*.tsx`) call
  `.toFixed()` directly inline rather than through `registry.tsx`. Updated both docs identically
  to name the real locations, kept the still-accurate "no web/src/charts/ directory" clause
  unchanged. Strategy: e (structural/connectivity — grep-verified). Blast radius:
  local+reversible.
