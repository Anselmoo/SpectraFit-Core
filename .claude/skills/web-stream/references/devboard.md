# Devboard reference — dashboard panels, HTML export, visx plot mounts

Self-contained essentials. Historical specialist content is in git
history under `.claude/skills/spectrafit-devboard/` (removed after
consolidation).

## Architecture facts (anchored from CLAUDE.md)

- **3 destinations** in evidence order: **Standing** (`#standing`,
  default — gate PASS/FAIL, geomean speedup, win rate, render-truth
  money figure), **Audit** (`#audit` — verification-wire matrix W1–W7
  + failure-mode taxonomy), **Evidence** (`#evidence` — all backends).
- Evidence has two sub-views: `overview` (all cases) and `case`
  (single-case drill-down). `#case=<id>` permalink routes to Evidence.
- Every panel is a `PanelRecord` in
  `web/src/panels/registry.tsx` (**single source of truth**).
- Each destination renders via `renderPanels(dest, report, ctx)`
  (`web/src/shell/renderPanels.tsx`).
- `Shell.tsx` is a thin (~110 ln) nav + destination switch.
- SVG charts mount through `web/src/plots/PlotMount.tsx`
  (ResizeObserver + `replaceChildren`, responsive width, isolated from
  React reconciliation). **Never** imperative `appendChild` into a
  React-managed div.
- Binding has **no silent `?? PRIMARY` fallback**; backends enumerate
  via `solversOf(report)` — no hardcoded backend ids.

## Offline path

`uv run poe report_html` bundles the data into a ~12 MB self-contained
`report.html` (data inlined; opens offline, no server) under
`.spectrafit_reports/benchmark/<run>/report.html`. Use for archival,
sharing, or CI artifacts.

## Number formatting

Inline in `web/src/panels/registry.tsx` (`.toFixed()`) plus the
collapse-proof tick formatter `tickLabels` in `web/src/series`. There
is **no** `web/src/charts/` directory or `fmtSpeedup`/`fmtPct`/
`fmtOrDash`/`fmtNum` module — those were dropped in the greenfield
rebuild; do not reference them.

## Tests that guard the architecture

- `web/src/__tests__/noHardcodedBackend.test.ts` — vitest source-scan
  forbidding `prof("spectrafit")`, `profiles.spectrafit`, and array
  literals starting `["spectrafit", "lmfit", …]`. A view file that
  picks up any of these patterns fails the check.
- `web/src/__tests__/contractCoverage.test.ts` — classifies every
  contract leaf as rendered or ignored.

## Stuck-mode entry

A dashboard panel that reopens is usually one of: a missing
`PanelRecord` entry, a `solversOf` fallback that snuck in, or a chart
mount that bypassed `PlotMount`. Curiosity sub-cycle:
`mcp__serena__find_referencing_symbols PanelRecord` and
`find_referencing_symbols PlotMount`.
