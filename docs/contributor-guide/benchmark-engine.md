# Benchmark engine (internal)

!!! note
    This page documents `python/oracles/` — the benchmark and cross-verification
    harness used to develop and audit spectrafit-core. It is **not** part of the
    stable public API described in [Python: core API](../reference/python/core-api.md);
    it may change without notice between releases.

`python/oracles/` compares **spectrafit** (the Rust kernel, the subject under
test) against **lmfit** and **jax/optimistix** (independent cross-verification
oracles) across a deterministic case catalog. It is test infrastructure —
scenarios, synthetic data, oracle math, and a verification & validation (V&V)
harness — imported by the benchmark CLI at run time and by `pytest` at
collection time.

## Key pieces a contributor will touch

- **`oracles.models.MODEL_REGISTRY`** — one `PeakModel` entry per model
  (numpy formula + `spectrafit_type` + param names + jax support flag). This
  is the parity oracle: its `evaluate` function must be numerically identical
  to the Rust kernel, since any formula difference shows up as a |Δr²| gate
  failure rather than a crash.
- **`oracles.cases`** — `CaseSpec` (a fully concrete, serializable benchmark
  case) and `CaseFamily` (a declarative generator that expands into many
  concrete `CaseSpec`s), organized by `CATEGORY_REGISTRY` (easy / complex /
  scaling / lineshapes / reality / edge / optfn / fixed / tied).
- **`oracles.bench_contract`** — the frozen `BenchReport` Pydantic contract:
  the single source of truth served at runtime by `oracles.api`'s FastAPI app,
  from which the web dashboard's TypeScript types are generated
  (`openapi-typescript`) — never hand-kept in sync.
- **`oracles.cli`** — the Typer CLI (`python -m oracles.cli run` / `gate`)
  that runs the benchmark and enforces the regression gate (spectrafit must
  not be slower than the baseline solver, and accuracy parity must hold on the
  LM-family cases).
- **`oracles.migrate`** — the `MIGRATIONS` registry for `BenchReport` schema
  version upgrades (additive minor vs. breaking major, see `DECISIONS.md`).

## Adding a case for an existing model

A single `CaseSpec`/`CaseFamily` entry in `oracles/cases.py` referencing an
existing model registry key. Adding a *new model* is a larger, multi-crate
change — see [Adding a model](../how-to/adding-a-model.md) for the
library-contributor subset, and the repo root `CLAUDE.md`'s "Adding a New
Benchmark Model" section for the full sequence including this benchmark
registry step.

## Regenerating the contract

After any change to `oracles/bench_contract.py` (or `oracles/contract.py`,
the small shared-leaf module holding `SolverMeta`), regenerate all three
checked-in schema mirrors with `uv run poe contract_regen` — it drives one
live API instance and writes the Python golden, `web/src/openapi.gen.ts`, and
`web/openapi.snapshot.json` in one pass.
