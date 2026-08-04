---
icon: lucide/cpu
---

# Benchmark engine

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
  LM-family cases). The latest results are published at
  [/report.html](/report.html) — the GitHub mirror rebuilds weekly, so it may
  lag the GitLab pipeline by up to seven days.
- **`oracles.migrate`** — the `MIGRATIONS` registry for `BenchReport` schema
  version upgrades (additive minor vs. breaking major, see `DECISIONS.md`).

## Adding a case for an existing model

A single `CaseSpec`/`CaseFamily` entry in `oracles/cases.py` referencing an
existing model registry key. Adding a *new model* is a larger, multi-crate
change — see [Adding a model](../how-to/adding-a-model.md) for the
library-contributor subset (Rust kernel + `ModelTypeStr` wiring), and
[Adding a new benchmark model](#adding-a-new-benchmark-model) below for the
full sequence including this benchmark registry step.

## Adding a new benchmark model

This is the step that comes *after* [Adding a model](../how-to/adding-a-model.md)
has landed the Rust kernel and the `ModelTypeStr`/`ModelType` wiring. It makes
the new shape fittable and benchmarked here in `python/oracles/`.

1. **Register a `PeakModel` in `oracles/models.py`.** Write a numpy
   `evaluate(x, **params) -> y` formula function, then add a `PeakModel(...)`
   entry to the `_BUILTIN_MODELS` tuple (`models.py:555` onward): `key`
   (registry/case key), `spectrafit_type` (must be a real `ModelType` member
   name — validated at registration time by
   `PeakModel._spectrafit_type_is_known_member`), `param_names`, `evaluate`,
   and optionally `formula_latex` / `jax_supported` / `extra_defaults`. This
   `evaluate` formula *is* the parity oracle: it must be numerically
   identical to the Rust kernel, or
   `tests/unit/oracles/test_wheel_eval.py`'s `wheel_parity_pairs()` will
   catch the mismatch as a |Δr²| gate failure rather than a crash.
2. **Add a typed component spec in `oracles/cases.py`.** If the new shape is
   a peak that case families should generate, add a `_Component` subclass
   (e.g. `GaussianSpec` at `cases.py:185`) with a `Literal["<key>"]` `model`
   discriminator and its own validated fields, then add a `case "<key>":` arm
   to `_peak()`'s `match model:` dispatch (`cases.py:587-622`) so
   `CaseFamily` generators can place it.
3. **Exercise it in a category.** Add the key to the model list a
   `CaseFamily` iterates — e.g. `_EASY_MODELS` (`cases.py:730`) for the
   `easy` category — or register a new `CategoryDef` entry in
   `CATEGORY_REGISTRY` (`cases.py:55`) if it needs its own category.
   Category `count` is diversity-driven and asserted against the generator
   grid in tests, so update both together.
4. **jax support is opt-in per-shape, not automatic.** Setting
   `jax_supported=True` in step 1 also requires a `case "<key>":` kernel
   branch in `oracles/backends/_jax.py::_kernel` (around line 176) — the
   per-component layout is derived from the registry, but the jax math for
   each shape is not.
5. **Regenerate the contract if needed.** Adding a model usually doesn't
   change `bench_contract.py`/`contract.py`; if it does, run
   `uv run poe contract_regen`.
6. **Verify.** Run `uv run pytest tests/unit/oracles/test_wheel_eval.py`
   (Rust/numpy parity for the new model) and `uv run poe benchmark_gate`
   (the regression gate must still pass with the new model in the mix).

Worked examples: any existing `_BUILTIN_MODELS` entry in `oracles/models.py`
plus its `_peak()` arm in `cases.py` (e.g. `gaussian`, `fano`, `pearson7`)
shows the full pattern end-to-end.

## Regenerating the contract

After any change to `oracles/bench_contract.py` (or `oracles/contract.py`,
the small shared-leaf module holding `SolverMeta`), regenerate all three
checked-in schema mirrors with `uv run poe contract_regen` — it drives one
live API instance and writes the Python golden, `web/src/openapi.gen.ts`, and
`web/openapi.snapshot.json` in one pass.
