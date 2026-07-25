---
type: gap
title: "[Medium] ui-audit: clickable-row-no-role"
description: "web/src/chrome/table.tsx:37 — clickable-row-no-role"
tags: ["kind:bug", "status:closed", "domain:ui-audit", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `web/src/chrome/table.tsx:37`
- Finding domain: ui-audit
- Suggested fix / explanation: Add `role="button"` (or wrap the interactive cell content in a real `<button>`/`<a>`) to the clickable `<tr>` so assistive tech announces it as actionable, matching the keyboard handling that's already implemented.
- Resolved by: [[evidence/phase-1-a11y-ev1]]
- Proposal: Added role="button" to the clickable suite-table row, only when interactive (table.tsx:37-38). Strategy: a. Blast radius: local+reversible.
