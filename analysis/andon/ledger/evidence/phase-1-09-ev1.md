---
type: evidence
title: "CLAUDE.md Native-showcases file citation matches reality"
description: "Independent verification confirms the corrected CLAUDE.md:349-351 citation of web/src/shell/EvidenceOverview.tsx (not EvidencePanel.tsx) for the Native showcases section."
resource: "web/src/shell/EvidenceOverview.tsx"
tags: ["strategy:e", "tier:3"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: CLAUDE.md (docs) -> web/src/shell/EvidenceOverview.tsx (code, phase-1/spectrafit-benchmark-web)
- Verdict: green
- Strategy detail: Tier 3 (grep/read-based, dispatched independently, blind to fix author's reasoning).
  EvidenceOverview.tsx:50,81 confirmed to contain the "Native showcases" nav link + heading;
  EvidencePanel.tsx confirmed to contain no such text anywhere, and its own header comment
  documents it as pure routing glue delegating to EvidenceOverview/EvidenceCaseView.
- Non-overridable: false
