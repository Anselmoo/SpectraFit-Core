> Applies to: tests/**/*.py

# TDD Routing

These rules apply whenever a test file is in context. They tell you which agent to invoke when a test fails.

## Rules

- Always run tests from repo root: `uv run pytest --tb=line -q`
- For targeted runs: `uv run pytest tests/test_<module>.py -v`
- Never fix test failures by editing test files first — diagnose source first.
- Use `spectrafit-tdd` agent for automatic routing when multiple test files fail simultaneously.
- For benchmark-related TDD loops, run fast speedboat evidence first and keep feedback under ~30 seconds when possible.
- Run full/publication benchmark suites only when the task is close to closure (final verification before handoff/merge).

## Component-to-agent routing table

| Test file | Source component | Agent to invoke |
|---|---|---|
| `test_models*.py` | Rust model kernels or Python schema | `spectrafit-rust-models` → `spectrafit-schemas` |
| `test_fit*.py` | PyO3 boundary / solver | `spectrafit-bindings` → `spectrafit-solver` |
| `test_benchmark*.py` | Benchmark scenarios / backends | `spectrafit-benchmark` → `spectrafit-performance-recovery` |
| `test_graph*.py` | DAG compiler / executor | `spectrafit-dag-engine` |
| `test_result*.py` | Result/schema layer | `spectrafit-schemas` |
| `test_boundary*.py` | JSON boundary / bindings | `spectrafit-bindings` → `spectrafit-schemas` |
| `test_evaluate*.py` | Evaluate binding | `spectrafit-bindings` → `spectrafit-solver` |
| `test_global_fit*.py` | Solver / multi-peak | `spectrafit-solver` → `spectrafit-bindings` |
| `test_cases*.py` | Schema + model parity | `spectrafit-schemas` → `spectrafit-rust-models` |
| `tests/extras/**` | Dashboard / eval board | `spectrafit-devboard` → `spectrafit-eval-board` |

## Error type heuristics

- `ImportError` / `ModuleNotFoundError` → check `python/spectrafit_core/__init__.py` and `_core.pyi` before routing; likely `spectrafit-bindings`
- `ValidationError` (Pydantic) → `spectrafit-schemas`
- `AssertionError` on numeric values → `spectrafit-rust-models` (wrong math) or `spectrafit-solver` (convergence)
- `PanicException` / Rust panic → `spectrafit-bindings`
- `KeyError` / `AttributeError` on result dict → `spectrafit-schemas`

## TDD workflow

1. Write the failing test (red)
2. Check which component owns it via the routing table above
3. Invoke the matching agent with the test file + error as context
4. Agent fixes source; re-run test to confirm green
5. If benchmark-related, run fast lane first: `PYTHONPATH=python uv run python -c "from benchmarkmark.runners.runner import run_suite; run_suite(category='tdd-speedboat-fast', mode='speedboat')"`
6. Confirm no regressions: `uv run pytest --tb=short`
7. Near close-out, run full/publication benchmark suite once for final evidence: `PYTHONPATH=python uv run python -c "from benchmarkmark.runners.runner import run_suite; run_suite(category='publication-benchmarks', mode='all')"`.

## Do not

- Do not invoke `spectrafit-performance-recovery` for test failures — only for benchmark regressions.
- Do not invoke multiple agents simultaneously for the same test failure — route to primary first.
- Do not skip the routing table and directly edit source for failures you have not diagnosed.
