---
type: gap
title: "[High/Low] ui-audit: low-contrast-pair + hardcoded-color-duplicate (tokens.css)"
description: "web/src/style/tokens.css:152 (low-contrast-pair), :117 (hardcoded-color-duplicate)"
tags: ["kind:bug", "status:closed", "domain:ui-audit", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: true
- Location: `web/src/style/tokens.css:152` (`.absent-note`'s text color) and `:117`
  (`.ev-rail`'s background)
- Finding domain: ui-audit (2 findings)
- Suggested fix / explanation: static heuristic flags for a plausibly low-contrast literal color
  pair, and a hardcoded color value that duplicates an existing design token.
- Resolved by: [[evidence/unattributed-tokens-ev1]]
- Proposal: (1) Low-contrast-pair — did NOT trust the static heuristic alone; computed the actual
  WCAG 2.1 contrast ratio via a real OKLCH→sRGB→relative-luminance conversion (not a Rung 4
  visual guess): `.absent-note`'s text color `var(--prov-absent)` (`oklch(0.45 0.01 250)`) on
  `--bg` (`oklch(0.17 0.012 250)`) gives **2.57:1** — well below the 4.5:1 WCAG AA floor for
  normal text (`.absent-note` renders at 0.82rem, not large text). Confirmed this is a genuine
  defect, not a false positive. `--prov-absent` is ALSO used by `.prov-absent` (a deliberately
  faint certainty-gradient dot/marker, further muted by `opacity: 0.5`, part of an intentional
  measured→absent visual gradient) — raising that shared token's lightness would blur the
  gradient's intended faintness for its OTHER, non-text usage. Instead added a new dedicated
  token `--absent-text: oklch(0.60 0.01 250)` (verified via the same contrast calculation: 4.85:1,
  clears AA with margin) used only by `.absent-note`'s actual paragraph text, leaving
  `--prov-absent`'s existing value and its `.prov-absent` marker usage untouched. (2)
  Hardcoded-color-duplicate — `.ev-rail`'s `background: oklch(0.17 0.012 250 / 0.7)` is a literal
  duplicate of `--bg`'s value with an added alpha. Added `--bg-translucent:
  oklch(0.17 0.012 250 / 0.7)` to `:root` (documenting the relationship to `--bg` inline, matching
  the file's own established pattern of paired base/alpha tokens, e.g. `--c-spectrafit` /
  `--c-spectrafit-soft`) and swapped the literal for `var(--bg-translucent)`. Verified: no test
  file references either changed token or selector by name (grepped); full vitest suite
  (563/563) and `npx tsc --noEmit` both clean after the change. Strategy: f (property/invariant —
  a real, computed WCAG contrast ratio, not a static-heuristic guess) for the contrast fix; a for
  the token-dedup fix. Blast radius: local+reversible.
