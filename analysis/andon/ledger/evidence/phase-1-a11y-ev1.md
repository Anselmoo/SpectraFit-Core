---
type: evidence
title: "role=img + role=button a11y fixes pass existing test suite"
description: "Rung 2 deterministic evidence: table.test.tsx + narrative.test.tsx + methods.wireMatrix.test.tsx (26 tests) pass after adding role attributes for gaps 11-12."
resource: "web/src/chrome/table.test.tsx"
tags: ["strategy:a", "tier:1"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gaps phase-1-11, phase-1-12 (code, phase-1/spectrafit-benchmark-web)
- Verdict: green
- Strategy detail: Rung 2 (rendered-deterministic). Added `role="img"` to the wire-status dot
  (components.tsx:136) and `role="button"` to the clickable suite-table row, only when it is
  actually interactive (table.tsx:37-38). The three test files exercising these exact components
  (table.test.tsx, narrative.test.tsx, methods.wireMatrix.test.tsx — 26 tests total) all pass,
  confirming no existing assertion on the DOM shape broke. Full project vitest run (563/563) also
  green, confirming no downstream consumer of these components broke either.
- Non-overridable: false
