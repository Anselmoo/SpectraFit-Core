---
type: gap
title: "[Medium] ui-audit: aria-label-on-non-interactive-span"
description: "web/src/narrative/components.tsx:136 — aria-label-on-non-interactive-span"
tags: ["kind:bug", "status:closed", "domain:ui-audit", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `web/src/narrative/components.tsx:136`
- Finding domain: ui-audit
- Suggested fix / explanation: Add `role="img"` (or `role="status"`) to the dot span alongside the existing aria-label so its accessible name is guaranteed to be exposed, or move the status text into visually-hidden text adjacent to the dot.
- Resolved by: [[evidence/phase-1-a11y-ev1]]
- Proposal: Added role="img" to the wire-status dot span (components.tsx:136) so its aria-label is reliably exposed. Strategy: a (tribunal not needed — Rung 2 test evidence sufficed). Blast radius: local+reversible.
