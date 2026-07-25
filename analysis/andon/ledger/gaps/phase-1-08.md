---
type: gap
title: "[Medium] code-idiom: long-function"
description: "web/src/panels/bodies/methods.tsx:202 — long-function"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `web/src/panels/bodies/methods.tsx:202`
- Finding domain: code-idiom
- Suggested fix / explanation: Extract the table rows / dataset summary into a separate small component or a `nistRows()` data-only helper, keeping the top-level function to composition.
- Resolved by: [[evidence/phase-1-08-ev1]]
- Proposal: Decomposed NistValidationCard (217 lines) into PassIcon, NistDatasetRow, and NistDatasetTable sub-components, leaving NistValidationCard as pure composition (81 lines). Strategy: a. Blast radius: local+reversible.
