---
type: evidence
title: "CLAUDE.md contract/index.ts export list matches reality"
description: "Independent Tier 3 structural check confirms the corrected CLAUDE.md:294-297 paragraph's 17-name export list exactly matches web/src/contract/index.ts's actual export type statements (membership and order)."
resource: "web/src/contract/index.ts"
tags: ["strategy:e", "tier:3"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: CLAUDE.md (docs) -> web/src/contract/index.ts (code, phase-1/spectrafit-benchmark-web)
- Verdict: green
- Strategy detail: Tier 1 (persistent Kythe/SCIP/LSIF index) unavailable — no index built for this repo.
  Tier 2 (LSP tool) attempted — no TypeScript language server configured in this environment
  ("No LSP server available for file type: .ts"). Fell through to Tier 3: dispatched the
  `self-assess:stage-mapper` agent directly, blind to the fix author's own reasoning, to
  independently re-derive both the file's actual `export type` list and CLAUDE.md's claimed list
  from scratch and compare them. Result: 17/17 names match exactly, same order. Advisory/non-blocking
  confidence per Tier 3's documented labeling (not Tier 1/2 strength), but no contradiction found.
- Non-overridable: false
