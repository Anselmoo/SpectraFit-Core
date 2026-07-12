# Tests reference — pytest coverage, quick_validation, deterministic fixtures

Self-contained essentials for the pytest suite. Historical content
lives in git history under `.claude/skills/spectrafit-tests/`.

## Conventions

- **Deterministic by default**: every MC test pins a seed.
  `quick_validation/` reproducers use a single seed, no MC loop.
- **`np.allclose` discipline**: state both `atol=` and `rtol=` — never
  rely on defaults (1e-8 vs 1e-5 differ across NumPy versions).
- **Fixtures are immutable**: tests must not mutate `tests/fixtures/`
  files; load + copy. NIST StRD fixtures are hook-guarded.
- **Phase-8**: tests under `tests/phase_8/` run in CI; everything else
  is opt-in.

## python-stream contract additions

1. **Composition with TDD**: in `python-stream` mode, the test goes
   first via `superpowers:test-driven-development`. The Pydantic
   round-trip is often the cleanest failing-test form for contract
   changes.
2. **`mcp__analyzer__ruff-check-ci` + `mcp__analyzer__ty-check`** must
   run green before claiming a test fix is done.

## Quick paths

- Test root: `tests/`.
- Quick-validation reproducers: `tests/quick_validation/` (deterministic;
  no MC).
- Fixtures: `tests/fixtures/` (NIST StRD guarded by
  `protect-nist-fixtures.sh` — never edit by hand).
- Bench seeds: `python/oracles/cases.py` `CaseSpec.seed` defines per-case
  MC repeatability.

## Stuck-mode entry

A flaky test that reopens after a "fix" usually means a hidden MC seed
dependency or fixture mutation. Curiosity sub-cycle:
`mcp__serena__find_referencing_symbols <fixture_name>` to find every
test that consumes it.
