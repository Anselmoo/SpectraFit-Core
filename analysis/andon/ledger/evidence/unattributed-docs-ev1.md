---
type: evidence
title: "Docs batch (MODELS.md/DECISIONS.md/CHANGELOG.md/MODELS_CATALOG.md) and tokens.css fixes verified"
description: "Independent verification confirms the amplitude-semantics correction (MODELS.md exp_gaussian callout, new DECISIONS.md ADR with old entry's prose untouched, CHANGELOG.md forward-note), the ModelTypeStr::as_str() correction in MODELS_CATALOG.md, and the tokens.css WCAG contrast fix (computed independently, matching claimed numbers) plus the hardcoded-color dedup."
resource: "MODELS.md, DECISIONS.md, CHANGELOG.md, python/oracles/MODELS_CATALOG.md, web/src/style/tokens.css"
tags: ["strategy:f", "tier:2"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gaps unattributed-13, unattributed-14, unattributed-15
- Verdict: green (all 5 sub-fixes)
- Strategy detail: f (property/invariant — WCAG contrast is a computable, checkable invariant, not
  a subjective judgment) for the tokens.css contrast fix; e (structural/connectivity) for the
  rest. Independent reviewer confirmed MODELS.md's own convention text requires per-section
  exception callouts, and independently verified the EMG area-normalization identity by reading
  emg.rs's eval() formula (matches the canonical EMG PDF parameterization). Confirmed DECISIONS.md
  old entry's Context/Decision/Rationale/Trade-offs are byte-identical pre/post (only the Status
  line changed) via git diff showing exactly one hunk on that entry; independently re-verified all
  3 "not area" models (voigt_true.rs, skewed_gaussian.rs, doniach.rs) by reading their eval()
  functions and confirming what eval(center) reduces to for each. Confirmed CHANGELOG.md's new
  note follows the same forward-pointing pattern as the pre-existing "F13 tree consolidation"
  entry, with zero diff on the original entry it corrects. Confirmed MODELTypeStr::as_str()
  genuinely exists (crates/spectrafit-types/src/types.rs) and is read by both
  spectrafit-graph::compiler and spectrafit-varpro, and confirmed zero remaining
  model_type_to_str function definitions anywhere in crates/ (only a historical comment).
  For tokens.css, independently ran a full OKLCH->linear-sRGB->gamma->WCAG-relative-luminance
  pipeline and got 2.572:1 (--prov-absent, fails AA) and 4.848:1 (--absent-text, passes AA),
  matching the claimed ~2.57/~4.85 numbers; confirmed .prov-absent's own rule is untouched, --bg
  is unchanged, and --bg-translucent is a pure literal-to-token refactor. Independently ran
  `npm run test` (563/563 passed) and `npx tsc --noEmit` (clean) after the tokens.css change.
- Non-overridable: false
