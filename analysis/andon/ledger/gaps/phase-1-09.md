---
type: gap
title: "[Medium] docs-drift: The Python engine fits a genuine N-D (3-D) problem with the parametric gaussian_nd kernel (_multidim, SP-2)... and a sha"
description: "web/src/shell/EvidenceOverview.tsx:50 — The Python engine fits a genuine N-D (3-D) problem with the parametric gaussian_nd kernel (_multidim, SP-2)... and a shared-model multi-spectrum global fit via a GlobalFitGraph joint fit (_global_fit)"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `web/src/shell/EvidenceOverview.tsx:50`
- Finding domain: docs-drift
- Suggested fix / explanation: The 'Native showcases' section is real and does render inside Evidence's overview sub-view, but the file it actually lives in is web/src/shell/EvidenceOverview.tsx, not web/src/shell/EvidencePanel.tsx as cited. EvidencePanel.tsx is now just routing g
- Resolved by: [[evidence/phase-1-09-ev1]]
- Proposal: Corrected CLAUDE.md:349-351's file citation from EvidencePanel.tsx to EvidenceOverview.tsx (where the "Native showcases" section actually lives), noting EvidencePanel.tsx is routing glue. Strategy: e, Tier 3. Blast radius: local+reversible.
