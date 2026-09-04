# Benchmark-web reference — BenchReport contract on the web side

Self-contained essentials. Historical specialist content lives in git
history under `.claude/skills/spectrafit-benchmark/`.

## Contract regen flow (anchored from CLAUDE.md)

TypeScript types are generated from the **live** OpenAPI schema the
FastAPI app publishes for the Pydantic contract — there is no hand-kept
JSON Schema. After any change to `python/oracles/contract.py`:

1. Serve the API: `uv run poe serve` (publishes `/openapi.json`).
2. `cd web && npm run contract` → runs
   `openapi-typescript http://localhost:8000/openapi.json`, writing
   `web/src/openapi.gen.ts`. `web/src/contract.ts` re-exports the
   named view types (`BenchReport`, `Featured`, `SuiteCase`,
   `BackendProfile`, `SolverMeta`, `SpreadPt`, `Point2D`, `MultiDim`,
   `Projection`, `TimeResolved`, `TimeSlice`, `PeakTrace`).

The `contract-sync-reminder.sh` hook nudges (non-blocking) when
`contract.py` is edited. The `pre-merge-schema-sync.sh` is the pre-merge
gate that the contract round-trips.

## Reading the latest run

- Latest manifest: `oracles.reports.latest_results()` returns the most
  recent `.spectrafit_reports/<category>/<YYYY-MM-DD>_run_NNN/`.
- Keys that matter (consume via typed BenchReport accessors, never
  dict-key access):
  - `baseline_solver_id` — which solver is `× 1.0` (default `lmfit`).
  - `geomean_speedup_vs_baseline` (canonical) +
    `geomean_speedup_vs_lmfit` (one-cycle legacy alias). Always read the
    canonical key first.
  - `max_abs_delta_r2`, `spectrafit_win_rate`, `regressions`,
    `regression_case_ids`.

## Backend enumeration

**Never** hardcode backend ids. Always:

```ts
import { solversOf } from "@/contract";
solversOf(report).forEach(...)
```

The `web/src/__tests__/noHardcodedBackend.test.ts` source-scan forbids:

- `prof("spectrafit")`
- `profiles.spectrafit`
- `[\s*["']spectrafit["']\s*,\s*["']lmfit["']`

Any view picking these up fails the source-scan.

## Stuck-mode entry

A web panel that reopens after a contract change is usually a missing
re-export in `web/src/contract.ts` or a typed-accessor that was added
to the contract but not threaded through the panel. Curiosity:
`mcp__serena__find_symbol <NewField>` and
`find_referencing_symbols BenchReport`.
