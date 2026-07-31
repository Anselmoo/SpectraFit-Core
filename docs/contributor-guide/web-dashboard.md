# Web Dashboard

Vite + React dashboard for the spectrafit benchmark. It fetches `/api/report`
from the FastAPI service in `python/oracles/` and renders it as three
destinations — Standing (verdict), Audit (verification), Evidence (data) —
each a declarative `PanelRecord` in `src/panels/registry.tsx`.

## Run locally

The dashboard proxies `/api` to a live API on `:8000`, so start that first,
from the repo root:

```bash
uv run poe serve        # FastAPI on :8000, serves /api/report
```

Then, from `web/`:

```bash
npm install
npm run dev              # Vite dev server on :5173, proxies /api -> :8000
```

## Tests

```bash
npx vitest run           # or: npm run test
```

`tsc --noEmit` (via `npm run build` / `npm run typecheck`) is the type-check
gate; there is also a Playwright e2e suite driven from the repo root via
`uv run poe web_e2e` (needs both the API and Vite dev server up).

## Regenerating the OpenAPI contract

The TypeScript types in `src/openapi.gen.ts` are generated from the live
OpenAPI schema published by the FastAPI app — there is no hand-kept schema.
With the API running (`uv run poe serve`):

```bash
npm run contract          # openapi-typescript -> src/openapi.gen.ts
```

`src/contract/index.ts` re-exports the named view types from the generated file, so
downstream view code never needs to change. After any contract-affecting
change, prefer `uv run poe contract_regen` from the repo root — it
regenerates this file plus the two other checked-in schema mirrors
(`web/openapi.snapshot.json` and the Python golden) in one shot.

## Adding a dashboard panel

The dashboard panel registry (`src/panels/registry.tsx`) is the single source of truth — every panel (plot, table, card) is a declarative `PanelRecord` entry that specifies its title, destination, and rendering function.

### Panel record structure

Each `PanelRecord` carries:

- `id`: unique panel identifier (e.g., `"accuracy-parity"`)
- `dest`: destination (`"standing"` / `"evidence"` / removed `"audit"`)
- `scope`: visibility scope (`"static"` for Standing, `"overview"` or `"case"` for Evidence)
- `section`: grouping within the destination (e.g., `"sec-finding"`, `"sec-compare"`)
- `title`: panel heading (string or function of the report)
- `caption`: descriptive text shown below the title (optional; string or function)
- `make(r, ctx)`: render function that returns `SVGSVGElement` (for plots) or `ReactNode` (for composite panels)

### Adding a new panel

1. **Write a body function** in the appropriate module under `src/panels/bodies/`:
   - `standing.tsx` for `dest: "standing"`
   - `evidenceOverview.tsx` for `dest: "evidence", scope: "overview"`
   - `evidenceCase.tsx` for `dest: "evidence", scope: "case"`
   
   The function receives the `report` (the full `BenchReport`) and `ctx` (context metadata), and returns either an SVG element or React JSX. Plot panels use `PlotMount` for responsive SVG rendering; table panels use React components.

2. **Import the body function** at the top of `src/panels/registry.tsx`

3. **Add a record to `PANELS[]`** following the pattern of existing entries:

   ```typescript
   {
     id: "my-new-panel",
     dest: "evidence",
     scope: "overview",
     section: "sec-compare",
     title: "My panel title",
     caption: "Description shown below the title",
     make: (r, ctx) => myBodyFunction(r, ctx),
   }
   ```

4. **Run the tests** — the vitest suite includes a render-audit that checks every panel title is stable and no hardcoded backend IDs appear:
   ```bash
   npm run test
   ```

The registry renders all panels via `renderPanels(dest, report, ctx)` in `src/shell/renderPanels.tsx`, which filters by destination and scope — no conditional logic needed in your body function.

## More

For the full dev-server workflow — starting/stopping both servers, port
conflicts, offline `report.html` bundling, and the web verification loop —
see the root `CLAUDE.md`'s "Running & previewing the
dashboard" section.
