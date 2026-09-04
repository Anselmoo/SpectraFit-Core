> Applies to: **/*.{py,rs}

# Testing conventions

These rules define how to write, place, and run tests so results are reliable, fast, and measurable.

## Rules

- Test layout:
  - Python tests go under `tests/` and mirror package layout (`tests/test_module.py` for `python/spectrafit_core/module.py`).
  - Rust unit tests belong in the module files with `#[cfg(test)]`; integration tests in `tests/` and benchmarks in `benches/` (or use `criterion`).

- Test types and naming:
  - Unit tests: fast, isolated, no network or filesystem dependence.
  - Integration tests: may use small fixtures but must be stable and timeboxed.
  - Benchmarks: use `pytest-benchmark` (Python) and `criterion` (Rust) for reliable measurements.
  - Add a concise docstring to each pytest test function (`test_*`) so Ruff/pydocstyle checks remain green.

- Determinism & seeds:
  - Tests that use randomness must set and document a fixed seed; surface the seed via an env var (e.g., `SPECTRAFIT_TEST_SEED`).
- When replacing a CLI implementation used by integration tests, preserve previously-supported flags as compatibility aliases until tests and callers are migrated.
- For HTML report assertions that inspect embedded JSON fragments, accept both raw-quote and HTML-escaped-quote forms to avoid renderer-dependent false negatives.
- For SSR visx SVG report assertions, verify responsive anchoring behavior (`viewBox` plus `maxWidth`/`max-width`) instead of requiring `width="100%"`, because reports intentionally prevent SVG upscaling on wide layouts.

- Flaky tests:
  - Mark flaky tests explicitly and open a tracking issue; flaky tests should be excluded from enforced coverage thresholds until stabilized.
  - For optional backends (for example JAX in benchmark gates), treat explicit unavailable sentinels as unsupported and exclude them from convergence assertions instead of failing the gate.

- TDD & workflow:
  - Prefer tests-first (TDD) for new features. Small, focused tests make reviews faster and coverage easier to maintain.
  - Keep expensive benchmark fixtures opt-in: `autouse` session fixtures must not force heavy benchmark runs for smoke-only tests that do not request benchmark data.

## CI behavior

- Every PR must run unit and integration tests. Benchmarks may run on schedule or opt-in CI runs to avoid long PR times.

## Do not

- Do not rely on external network services in unit tests. Use recorded fixtures or service mocks.
