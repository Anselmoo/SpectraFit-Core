# Web Panel Registry Architecture (gen-3, post-2026-06-12)

## Core pattern
All panels are `PanelRecord` entries in `web/src/panels/registry.tsx` — single source of truth.
Each destination renders `renderPanels(dest, report, ctx)` (`web/src/shell/renderPanels.tsx`).
Shell.tsx is ~110 lines (nav + destination switch only).

## PanelRecord fields
- `id`: string — unique panel identifier
- `dest`: "standing" | "audit" | "evidence"
- `scope`: "overall" | "single" (evidence only; overall = all-cases, single = selected case)
- `section`: grouping label within destination
- `title`: display title
- `caption`: research-grade caption (cite methods, e.g. Dolan-Moré)
- `fullWidth?`: boolean — spans full grid width (default: half-width in 2-up grid)
- `make(report, ctx)`: returns a React node (typically a `<PlotMount>` wrapper)

## Module layout
```
web/src/
├── panels/
│   ├── registry.tsx     # PanelRecord[] — the only file to edit to add/remove panels
│   ├── types.ts         # PanelRecord, PanelScope, PanelCtx, scopeMatches
│   ├── chrome.tsx       # PanelCard, PanelTitle, Caption (shared chrome)
│   ├── PlotPanel.tsx    # PanelCard + responsive PlotMount
│   ├── taxonomy.ts      # FAILURE_MODES typed record
│   └── TaxonomyPanel.tsx
├── plots/
│   ├── PlotMount.tsx    # ResizeObserver → make(width) → replaceChildren; NEVER appendChild into React div
│   └── *.ts             # Observable Plot adapters; each accepts (rows, {colors, width?}) → SVGSVGElement
├── series/
│   └── *.ts             # Pure (report, selection) → typed rows; no DOM, no colors, no globals
├── shell/
│   ├── Shell.tsx        # ~110 ln: nav + destination switch
│   ├── StandingPanel.tsx
│   ├── AuditPanel.tsx
│   └── EvidencePanel.tsx  # view state: "overview" | "case"; #case=<id> permalink
└── style/
    └── tokens.css       # CSS variables; all panel/plot code uses var(--token) — no hardcoded values
```

## Evidence sub-views
- **Overview** (`scope: "overall"`): suite-table, saturation, delta-r2-ci, speedup-ci, winner-stability
- **Case** (`scope: "single"`): fit, peaks, recovery, pulls, convergence, timing, warmup, scaling, reproducibility, conditioning
- `#case=<id>` hash routes to Case sub-view at mount

## Anti-patterns enforced by tests
- `noHardcodedBackend.test.ts`: no `prof("spectrafit")`, no `profiles.spectrafit`, no `["spectrafit","lmfit",…]` literal
- `contractCoverage.test.ts`: every BenchReport leaf is "rendered by <module>" or "ignored: <reason>"
- No `?? PRIMARY` fallback — `solversOf(report)` enumerates backends

## Adding a panel (4-step pattern)
1. `web/src/series/<name>.ts` — pure `report → rows` (unit-tested, no DOM)
2. `web/src/plots/<name>.ts` — `(rows, {colors, width?}) → SVGSVGElement`
3. Add `PanelRecord` in `panels/registry.tsx` with dest/scope/section/title/caption/make
4. `cd web && npx vitest run` green + `npx playwright test dashboard-render-audit` green

## Layout tokens
```css
--layout-editorial: 760px;   /* Standing + Audit */
--layout-evidence: 1200px;   /* Evidence */
```

## Related
- `mem:package-layout-benchmark-oracles` — Python side
- `docs/_absorb/C1-decisions.md` — 2026-06-12 panel registry entry
