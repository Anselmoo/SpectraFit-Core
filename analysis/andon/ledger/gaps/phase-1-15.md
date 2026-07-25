---
type: gap
title: "[Low] code-idiom: unnecessary-any"
description: "web/src/panels/bodies/codeProvenance.tsx:55 — unnecessary-any"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `web/src/panels/bodies/codeProvenance.tsx:55`
- Finding domain: code-idiom
- Suggested fix / explanation: Type `suiteRow` as `SuiteCase | undefined` and `m` as `SuiteMetric | undefined`; use `f?.modelSourceFile` directly without a cast.
- Resolved by: [[evidence/phase-1-webtypes-ev1]]
- Proposal: Typed suiteRow as SuiteCase|undefined and m as SuiteMetric|undefined in codeProvenance.tsx, dropping the untagged any casts at lines 55/59/84 the eslint-disable didn't cover. Strategy: a. Blast radius: local+reversible.
