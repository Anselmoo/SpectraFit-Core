> Applies to: **/*.{py,rs}

# Performance benchmarking protocol

This file defines required behavior for performance work in spectrafit-core.

## Rules

- Treat the newest per-run results as the baseline source of truth for performance claims. Each `poe benchmark` run writes an isolated `.spectrafit_reports/benchmark/<YYYY-MM-DD>_run_NNN/results.json`; resolve it with `benchmarkmark.export.resolve_latest_results()` (or `find .spectrafit_reports/benchmark -name results.json | xargs ls -t | head -1`). The legacy `benchmark/results.json` is still refreshed as a back-compat "latest" copy.
- Separate one-time setup cost from per-iteration solve cost when evaluating optimization impact.
- Report robust statistics for every performance claim: median, IQR, and CV.
- Include before/after deltas for affected scenarios and scaling points.
- Validate correctness after performance edits:
  - `success` flags remain stable
  - `chi2`/`r2` remain within expected tolerance
  - parameter agreement is preserved when those checks are available
- Make minimal, measurable changes; implement and validate incrementally.
- If an optimization does not improve median performance in the target scenario, document it and roll back or deprioritize it.
- For outlier-heavy timings, explain whether conclusions are based on robust metrics instead of mean.
- Keep public APIs and schema compatibility unchanged unless a breaking change is explicitly approved.

## Do not

- Do not claim performance improvements using mean-only metrics.
- Do not merge unmeasured performance refactors.
- Do not change optimization scope and correctness scope in the same unverified step.
