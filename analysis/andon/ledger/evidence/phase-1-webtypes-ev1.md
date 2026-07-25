---
type: evidence
title: "unnecessary-any removals + fmtP consolidation + hex-fallback removal type-check clean"
description: "Rung 0-1 deterministic evidence: full project tsc --noEmit is clean and the full vitest suite (563/563, 97 files) passes after gaps 13-18, 21."
resource: "web/tsconfig.json"
tags: ["strategy:a", "tier:1"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gaps phase-1-13..18, phase-1-21 (code, phase-1/spectrafit-benchmark-web)
- Verdict: green
- Strategy detail: Rung 0 (type system) + Rung 2 (rendered-deterministic, vitest execution) —
  `npx tsc --noEmit -p tsconfig.json` clean (no errors) after removing all `as any` casts (gaps
  13-17), consolidating the duplicated `fmtP` helper into `web/src/series/format.ts` (gap 18), and
  dropping the hardcoded `--warn` hex fallback + duplicate GATE_COLOR map (gap 21). Full `vitest run`
  afterward: 97 files, 563 tests, all passing — this is comprehensive coverage of the touched panel
  bodies, not a narrow smoke check, so it is treated as sufficient deterministic evidence per the
  Detection Ladder ("climb only as high as the defect class requires") rather than escalating to a
  tribunal for these mechanical, type-checked substitutions.
- Non-overridable: false
