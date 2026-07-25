# TDD reference — routing failing pytest to the right specialist

Self-contained essentials for routing failing pytest. Historical content
lives in git history under `.claude/skills/spectrafit-tdd/`.

## Routing table

| Failure mode | Owning skill (post-consolidation) | Reference |
|--------------|-----------------------------------|-----------|
| `ImportError` / `ModuleNotFoundError` | `crates-stream` | `references/bindings.md` |
| `pydantic.ValidationError` on `BenchReport` | `python-stream` | `references/schemas.md` |
| Δr² regression vs the named baseline | `crates-stream` | `references/solver.md` |
| Flaky MC test (passes 9/10) | `python-stream` | `references/tests.md` |
| `pyo3::PanicException` | `crates-stream` | `references/bindings.md` |
| Contract round-trip failure | `python-stream` | `references/schemas.md` |
| Web vitest source-scan failure | `web-stream` | `references/devboard.md` |

## python-stream contract additions

`python-stream` already owns the python side of test failures. In
tri-stream mode this is the natural python sub-loop's first step:

1. Read the failing pytest output.
2. Classify (use the routing table from the absorbed skill).
3. If the classification points outside python-stream (e.g. ImportError
   → crates-stream bindings), hand off via the inter-stream wire.
4. Otherwise stay in-stream and pick the right reference.

## Quick paths

- Failure taxonomy: see absorbed skill's routing table.
- Quick repro: `tests/quick_validation/` (deterministic; one MC seed).
- Full regression: `uv run poe scenario_smoke` (fast cross-check).

## Stuck-mode entry

Mis-routed failures reopen — the curiosity sub-cycle re-classifies by
following `mcp__serena__find_referencing_symbols` from the test's
assertions back to the production code.
