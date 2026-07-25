---
type: evidence
title: "ARCHITECTURE.md compose.py comment matches reality"
description: "Independent verification confirms compose.py implements factory functions + a fluent ComposeBuilder, no operator-overload dunders."
resource: "python/spectrafit_core/compose.py"
tags: ["strategy:e", "tier:3"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: ARCHITECTURE.md (docs) -> python/spectrafit_core/compose.py (code, phase-1/spectrafit_core)
- Verdict: green
- Strategy detail: Tier 3, independent agent confirmed 31 factory functions plus ComposeBuilder's
  .bind().build() chaining (documented in the module's own docstring), and grepped the whole
  package for arithmetic/logical operator dunders (__add__/__radd__/__iadd__/etc.) — zero hits.
  Noted ComposeBuilder overrides __iter__ (an intentional Pydantic LSP break), which is iteration
  protocol, not operator overloading, so it does not contradict the corrected claim.
- Non-overridable: false
