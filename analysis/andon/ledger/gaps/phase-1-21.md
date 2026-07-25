---
type: gap
title: "[Low] ui-audit: hardcoded-color-fallback"
description: "web/src/shell/LivenessBanner.tsx:77 — hardcoded-color-fallback"
tags: ["kind:bug", "status:closed", "domain:ui-audit", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `web/src/shell/LivenessBanner.tsx:77`
- Finding domain: ui-audit
- Suggested fix / explanation: Drop the inline hex fallback (tokens.css is guaranteed to be loaded) or, if a fallback is genuinely needed for a resilience case, define it once as a shared TS constant re-exported from web/src/style/index.ts so there is one place to update it in loc
- Resolved by: [[evidence/phase-1-webtypes-ev1]]
- Proposal: Dropped the hardcoded `var(--warn, #d98c00)` hex fallback (4 sites) and replaced EvidenceVerdict.tsx's duplicate GATE_COLOR map with an import from shared.tsx's canonical one. Strategy: a. Blast radius: local+reversible.
