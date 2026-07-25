---
type: gap
title: "[Low] code-idiom: unnecessary-any"
description: "web/src/panels/bodies/standing.tsx:38 — unnecessary-any"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `web/src/panels/bodies/standing.tsx:38`
- Finding domain: code-idiom
- Suggested fix / explanation: Drop the `as any` casts and reference `report.suite` / `report.runTimestampUnix` directly (narrow to the local shape with a proper type/interface instead of `any` if a narrower view is genuinely needed).
- Resolved by: [[evidence/phase-1-webtypes-ev1]]
- Proposal: Dropped `(report.suite as any)` and `(report as any).runTimestampUnix` in standing.tsx:38,538 — report.suite/report.runTimestampUnix are already correctly typed. Strategy: a. Blast radius: local+reversible.
