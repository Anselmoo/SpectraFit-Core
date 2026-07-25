---
type: gap
title: "[Low] code-idiom: unnecessary-any"
description: "web/src/shell/ProvenanceFooter.tsx:26 — unnecessary-any"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `web/src/shell/ProvenanceFooter.tsx:26`
- Finding domain: code-idiom
- Suggested fix / explanation: Replace with `report.gitCommit`, `report.gitBranch`, `report.runTimestampUnix` — no cast required.
- Resolved by: [[evidence/phase-1-webtypes-ev1]]
- Proposal: Dropped 3 `(report as any).*` casts in ProvenanceFooter.tsx:26-28 — all three fields are already typed on BenchReport. Strategy: a. Blast radius: local+reversible.
