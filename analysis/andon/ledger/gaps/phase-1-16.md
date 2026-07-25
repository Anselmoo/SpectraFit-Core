---
type: gap
title: "[Low] code-idiom: unnecessary-any"
description: "web/src/shell/CaseScenario.tsx:19 — unnecessary-any"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `web/src/shell/CaseScenario.tsx:19`
- Finding domain: code-idiom
- Suggested fix / explanation: Drop the `as any` and use the `Featured | undefined` return value directly.
- Resolved by: [[evidence/phase-1-webtypes-ev1]]
- Proposal: Dropped the `as any` cast in CaseScenario.tsx:19 — analyzedById already returns Featured|undefined. Strategy: a. Blast radius: local+reversible.
