# spectrafit-core web

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

## More

For the full dev-server workflow — starting/stopping both servers, port
conflicts, offline `report.html` bundling, and the web verification loop —
see the root [`CLAUDE.md`](../CLAUDE.md)'s "Running & previewing the
dashboard" section.
