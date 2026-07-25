---
type: gap
title: "[Medium] code-idiom: long-function"
description: "web/src/panels/bodies/standing.tsx:528 — long-function"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `web/src/panels/bodies/standing.tsx:528`
- Finding domain: code-idiom
- Suggested fix / explanation: Split the data-derivation (runDate, optionalAbsent, facts) from rendering, and extract repeated inline-style blocks (masthead, fact rows) into small named subcomponents.
- Resolved by: [[evidence/phase-1-07-ev1]]
- Proposal: Decomposed factsLandingCard (257 lines) into computeRunDate + 4 sub-components (FactsMasthead, ResultsTable, EvidenceFlowLink, AbsentBackendNote), leaving factsLandingCard as pure composition (27 lines). Strategy: a. Blast radius: local+reversible.
