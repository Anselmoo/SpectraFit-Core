> Applies to: .spectrafit_reports/**/feedback.json

# Speedboat feedback routing

Use `feedback.json` as the source of truth for benchmark self-correction.

## Rules

- If `gates.overall` is `false`, read `recommendations[]` first and execute them in order.
- For each failing recommendation, open the corresponding per-test artifact JSON in the same run directory (`test_*.json`) and locate the backend with the lowest `r2` or largest `param_recovery` value.
- When `param_recovery` exceeds 5% for any parameter, adjust case seeds/noise in `python/benchmarkmark/cases.py` and backend initialization in `python/benchmarkmark/backends/*.py`.
- When a backend has `success: false`, treat it as a solver/setup issue and tune backend-specific guesses/bounds before changing gates.
- Re-run `pytest tests/speedboat/ -m speedboat` after each correction and verify a new numbered run folder is produced.
- Keep fixes deterministic: no random seed changes unless explicitly required by the failing recommendation.

## Do not

- Do not infer failures from HTML output when JSON artifacts are available.
- Do not edit gate thresholds first; fix scenario/backend behavior first.
- Do not mark a recommendation resolved without a new run artifact showing the updated metric.
