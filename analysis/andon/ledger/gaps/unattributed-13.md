---
type: gap
title: "[Medium/Low] lint-audit: amplitude-is-peak-value + modelsmd-authoritative (MODELS.md, DECISIONS.md, CHANGELOG.md)"
description: "MODELS.md:42, DECISIONS.md:6521, CHANGELOG.md:130 — same root-cause mischaracterization as phase-5 gaps 03/04, propagated to 3 more docs"
tags: ["kind:bug", "status:closed", "domain:lint-audit", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `MODELS.md:42`, `DECISIONS.md:6521` (actual line ~6589, shifted since the brief was
  generated), `CHANGELOG.md:130`
- Finding domain: lint-audit (3 findings, same root-cause class as phase-5's gaps 03/04)
- Suggested fix / explanation: MODELS.md's own convention framework (MODELS.md:14-18) requires
  amplitude-means-peak-value exceptions to be called out per section; DECISIONS.md and
  CHANGELOG.md both restate the same "area-normalised peak models (exp_gaussian,
  skewed_gaussian, doniach_sunjic, true_voigt)" overgeneralization already corrected in
  `postfit.rs` during Phase 5.
- Resolved by: [[evidence/unattributed-docs-ev1]]
- Proposal: (1) MODELS.md:42 — added the required inline exception callout to exp_gaussian's
  table row (`**A is the total integrated area..., not a peak height**`), matching the file's own
  established callout style (e.g. `σ is the **HWHM**` on the lorentzian/pearson7 rows). (2)
  DECISIONS.md — found the actual entry (line ~6589, "Off-domain runaway guard skips above r²
  floor (CX-017 class)", 2026-06-08) restating the same wrong 4-model claim. Per this file's own
  documented convention (line 4: "Each entry is append-only — superseded entries keep a
  `**Superseded by**` note"), did NOT rewrite the historical entry's prose — added a
  `**Superseded by**` note to its Status line, added a new dated ADR
  ("[2026-07-24] Correction: exp_gaussian is the only area-normalised-amplitude model") in the
  append-only section documenting the correction with the same verification evidence from Phase
  5, and added a matching Solver-topic-index line. (3) CHANGELOG.md:130 — same append-only
  convention already established there (the existing "F13 tree consolidation" entry sets the
  precedent: add a forward-pointing note in `[Unreleased]`, don't rewrite old release notes) —
  added a matching correction note pointing at the new DECISIONS.md ADR. Docs-only changes, no
  code/logic touched (the actual code fix already happened and was verified in Phase 5).
  Strategy: e (structural/connectivity — docs claim vs. MODELS.md's own authoritative table and
  the actual Rust kernels, already verified independently in Phase 5's evidence). Blast radius:
  local+reversible.
