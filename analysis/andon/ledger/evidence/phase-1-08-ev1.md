---
type: evidence
title: "NistValidationCard decomposition is behavior-preserving"
description: "Independent diff-trace verification (not just final-file review) confirms the PassIcon/NistDatasetRow/NistDatasetTable extraction from NistValidationCard preserves JSX, styles, thresholds, and formatting byte-for-byte, with correct key placement."
resource: "web/src/panels/bodies/methods.tsx"
tags: ["strategy:a", "tier:1"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gap phase-1-08 (code, phase-1/spectrafit-benchmark-web)
- Verdict: green
- Strategy detail: a (tribunal-equivalent single independent reviewer, Rung 1-2) — dispatched blind
  to the fix author's reasoning, instructed to pull `git diff HEAD` (not just read the final file)
  to compare against real pre-refactor code. Confirmed: 217-line original -> 81-line composition-only
  NistValidationCard; PassIcon/NistDatasetRow/NistDatasetTable reproduce styles/thresholds/precision
  formatting verbatim; key correctly moved to the NistDatasetRow call site inside .map(); no dead
  imports. Full vitest suite (563/563, incl. dedicated nistValidation.test.tsx) + clean tsc also
  passing. Flagged (informational, not a defect) that gap-18's fmtP change to scopeBoundariesCard
  rides along in the same file diff — expected, same file touched by two different gaps.
- Non-overridable: false
