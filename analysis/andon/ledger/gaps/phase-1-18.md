---
type: gap
title: "[Low] code-idiom: duplicated-magic-number"
description: "web/src/series/inferentialHeadline.ts:26 — duplicated-magic-number"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `web/src/series/inferentialHeadline.ts:26`
- Finding domain: code-idiom
- Suggested fix / explanation: Extract one shared `fmtP`/`fmtPValue` helper (e.g. in a shared formatting module) with a named `MIN_DISPLAYABLE_P = 0.0001` constant, and have all five call sites use it.
- Resolved by: [[evidence/phase-1-webtypes-ev1]]
- Proposal: Extracted the duplicated fmtP (+ MIN_DISPLAYABLE_P=0.0001) helper into web/src/series/format.ts, replacing 2 duplicate definitions (inferentialHeadline.ts, nestedAdequacy.tsx) and 2 inlined copies (standing.tsx x2, methods.tsx). Strategy: a. Blast radius: local+reversible.
