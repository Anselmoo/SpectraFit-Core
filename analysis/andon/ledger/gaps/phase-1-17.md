---
type: gap
title: "[Low] code-idiom: unnecessary-any"
description: "web/src/panels/bodies/constrainedFit.tsx:20 — unnecessary-any"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `web/src/panels/bodies/constrainedFit.tsx:20`
- Finding domain: code-idiom
- Suggested fix / explanation: Remove the `AnyRec` alias and type `analyzed`/`suiteById` against `Featured[]` / `SuiteCase` directly.
- Resolved by: [[evidence/phase-1-webtypes-ev1]]
- Proposal: Removed the AnyRec=any alias in constrainedFit.tsx, typed analyzed as Featured[] and suiteById as Map<string,SuiteCase>. Strategy: a. Blast radius: local+reversible.
