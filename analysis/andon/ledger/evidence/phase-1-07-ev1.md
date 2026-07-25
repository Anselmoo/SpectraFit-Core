---
type: evidence
title: "factsLandingCard decomposition is behavior-preserving"
description: "Independent diff-trace verification (git diff HEAD, not just final-file review) confirms the FactsMasthead/ResultsTable/EvidenceFlowLink/AbsentBackendNote extraction preserves JSX, styles, and conditional logic element-by-element."
resource: "web/src/panels/bodies/standing.tsx"
tags: ["strategy:a", "tier:1"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gap phase-1-07 (code, phase-1/spectrafit-benchmark-web)
- Verdict: green
- Strategy detail: a (single independent reviewer, Rung 1-2) — dispatched blind to the fix
  author's reasoning, instructed to diff against real HEAD (confirmed the original was exactly
  257 lines, matching the finding). Confirmed factsLandingCard is now a 27-line thin composer;
  all 4 extracted sub-components reproduce styles/conditionals/text verbatim, only prop-renamed
  (`m` -> `manifest`); computeRunDate's only change is dropping a redundant `as any` cast on an
  already-typed field. tsconfig's noUnusedLocals/noUnusedParameters + clean tsc mechanically rule
  out dead code. 138/138 tests pass across web/src/panels + web/src/shell. Flagged (informational)
  that gap-18's fmtP extraction rides along in the same file diff — expected, same file.
- Non-overridable: false
