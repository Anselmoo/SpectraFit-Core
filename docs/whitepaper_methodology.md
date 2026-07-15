# Methodology White Paper — Code Dualism and the Benchmark Method Break

Status: living document. Companion to [`ARCHITECTURE.md`](../ARCHITECTURE.md) and
[`MODELS.md`](../MODELS.md).

This paper documents two things that are easy to get wrong in a Rust/Python hybrid
fitting framework:

1. **Code dualism** — what Rust owns, what Python owns, and the single PyO3 seam
   that joins them.
2. **The benchmark "break in method"** — the benchmark generates synthetic data
   with one set of model formulas (pure-Python reference kernels) and fits it with
   a different implementation (the Rust core). This paper explains the fairness and
   validity implications, proposes a consistent methodology, and records the
   fairness invariants that are already standing rules.

---

## 1. Architecture / dualism map

spectrafit-core is one codebase with two languages joined at exactly one seam. The
guiding rule: **Rust owns the numerics; Python owns the schema, the high-level
API, and the benchmark harness.** Pydantic models on the Python side and serde
structs on the Rust side mirror each other and are exchanged as JSON across the
seam.

### Rust ownership

| Concern | Crate | Notable source |
|---|---|---|
| Model kernels (Gaussian, Lorentzian, Pseudo-Voigt/Voigt, Fano, polynomials, steps, double-exponential) + analytical Jacobians | `crates/spectrafit-models` | `gaussian.rs`, `lorentzian.rs`, `pseudo_voigt.rs`, `voigt.rs`, `fano.rs`, `polynomial.rs`, `step.rs`, `exponential.rs` |
| Solvers: Levenberg–Marquardt, trust-region reflective, IRLS, global (differential evolution) | `crates/spectrafit-solver` | `lm.rs`, `trf.rs`, `irls.rs`, `global.rs`, `problem.rs` |
| Variable projection (VarPro) | `crates/spectrafit-varpro` | `solver.rs`, `model.rs` |
| Graph compile / evaluate (DAG IR, expression trees) | `crates/spectrafit-graph` | `compiler.rs`, `executor.rs` |
| Schema / serde types and error model | `crates/spectrafit-types` | `types.rs`, `error.rs` |
| PyO3 binding crate | `crates/spectrafit-core` | `src/lib.rs` |

> Note: VarPro lives in its own crate (`crates/spectrafit-varpro`), not under
> `crates/spectrafit-solver`. The LM / TRF / IRLS / global routines are the modules
> declared in `crates/spectrafit-solver/src/lib.rs`.

### Python ownership

| Concern | Location |
|---|---|
| High-level fitting API (`fit`, `fit_fast`, `evaluate`, `evaluate_components`) | `python/spectrafit_core/` (`fit.py`, `evaluate.py`) |
| Pydantic schema mirror (`FitGraph`, `ModelNodeSpec`, `ModelType`, `FitOptions`, `MeasurementData`, `Parameter`, `FitResult`, …) | `python/spectrafit_core/` (`graph.py`, `models.py`, `options.py`, `data.py`, `parameters.py`, `result.py`) |
| Benchmark harness (cases, catalog, backends, runners, export) | `python/benchmark/` |

The Python `ModelType` enum (`python/spectrafit_core/models.py`) mirrors the Rust
`ModelType`; the `Rust ModelType` column in `MODELS.md` is the authoritative
mapping.

### The PyO3 boundary

There is exactly one FFI seam:

- **Rust side:** `crates/spectrafit-core/src/lib.rs` — five `#[pyfunction]`s
  registered in the `#[pymodule]`.
- **Python type stub:** `python/spectrafit_core/_core.pyi` — the typed mirror of
  those same five functions.

| Function | Inputs (JSON unless noted) | Output |
|---|---|---|
| `fit(graph_json, data_json, options_json)` | all JSON | result JSON string |
| `fit_arrays(graph_json, x, y, sigma, dataset_sizes, options_json)` | numpy arrays for `x`/`y`/`sigma` | result JSON string |
| `fit_arrays_numpy(graph_json, x, y, sigma, dataset_sizes, options_json)` | numpy arrays | `(compact result JSON, best_fit ndarray)` |
| `evaluate(graph_json, params_json, data_json)` | all JSON | JSON with `best_fit` array |
| `evaluate_components(graph_json, params_json, data_json)` | all JSON | per-node component JSON |

Everything crosses this seam as JSON-serialised Pydantic/serde structs, except the
measurement arrays in the `*_arrays*` paths, which are passed as raw numpy to skip
~2 ms of serialisation per call. This is the **only** place the two languages
touch; any new capability must be expressible as one of these five calls plus the
shared schema.

---

## 2. The benchmark "break in method"

### What the break is

The benchmark compares three backends:

- **spectrafit** — the Rust core (`python/benchmark/backends/_spectrafit.py`).
- **lmfit** — scipy/lmfit reference (`python/benchmark/backends/_lmfit.py`).
- **jax** — a JAX VarPro/least-squares path (`python/benchmark/backends/_jax.py`).

The synthetic data those backends fit is **not** produced by the Rust kernels. It
is produced by pure-Python reference kernels in
`python/benchmark/models.py` (`gaussian`, `lorentzian`, `pseudo_voigt`,
`fano`, `double_exponential`, `linear_bg`, `ackley_slice`, `rastrigin_slice`).
So the **data-generating model and the fitting model are different
implementations of the same formula.**

```
python/benchmark/models.py   →  synthetic y = f_python(x; θ_true) + noise
                                          │
                                          ▼
crates/spectrafit-models (Rust)     →  fit:  argmin_θ ‖ f_rust(x; θ) − y ‖
```

### Why this is both a feature and a hazard

**The upside (independent oracle).** Because the data is generated by an
*independent* implementation, a successful fit is evidence that the Rust kernel
agrees with a second, separately-written formula. If the Rust Gaussian had a sign
error or a factor-of-two in σ, fitting Python-generated Gaussian data would expose
it as poor recovery or low r². A self-consistent benchmark (fit Rust-generated
data with the Rust kernel) cannot catch that class of bug — it would fit its own
mistake perfectly.

**The hazard (silent formula drift).** The two implementations must encode the
*same* formula and the *same* parameter conventions (`MODELS.md`: amplitude = peak
value at center; width = σ, not FWHM, FWHM ≈ 2.355·σ; the Pseudo-Voigt mixing
weight is `fraction`, historically `eta`/`frac`). If the Python reference and the
Rust kernel drift — e.g. one uses FWHM where the other uses σ, or the Pseudo-Voigt
`fraction` convention flips — then:

- a real Rust regression can be **masked** (both move together if someone "fixes"
  the reference to match a buggy kernel), or
- a correct Rust kernel can be **penalised** for matching a stale reference,
  showing up as a spurious accuracy gap against lmfit/jax.

Today nothing *asserts* that `models.py` and `crates/spectrafit-models` compute the
same thing. The agreement is maintained by hand and by `MODELS.md` discipline. That
is the "break in method": the benchmark relies on an oracle whose parity with the
system under test is **assumed, not tested.**

A second, narrower break: the four multimodal surrogates (Ackley, Rastrigin,
Rosenbrock, Griewank) are not native Rust kernels at all. They are fit with a fixed
**3-Gaussian basis solved by the global (DE) optimizer** (`_PATHOLOGICAL_MODELS` in
`backends/_spectrafit.py`), so their reported r² reflects a basis ceiling rather
than solver convergence. This is documented in `MODELS.md` and is not the focus
here, but it means "accuracy" is not a single uniform metric across the catalog.

---

## 3. Proposed consistent methodology

Three options, with trade-offs.

### (a) Generate data from the same Rust kernels

Generate synthetic data by calling the Rust `evaluate` (via the PyO3 seam) and then
fit with the Rust solver.

- **Pro:** perfectly self-consistent; no formula-drift surface; one source of
  truth for each formula.
- **Con:** *destroys the independent oracle.* Any bug in a Rust kernel is now
  invisible — the data and the model share it. The benchmark becomes a pure
  solver/timing benchmark and stops validating kernel correctness. It also makes
  lmfit/jax look artificially worse if the Rust kernel has an idiosyncrasy they do
  not share.

### (b) Keep the Python reference kernel as an explicit oracle + parity test

Keep `python/benchmark/models.py` as the data generator, and **add a parity
test** that asserts, for every model, that the Python reference and the Rust kernel
agree to a tolerance over a sampled x-grid and a spread of parameters:

```text
for model in catalog:
    y_py   = models.<fn>(x, **θ)                      # python reference
    y_rust = evaluate(graph_for(model, θ), x)         # PyO3 → Rust kernel
    assert allclose(y_py, y_rust, rtol=PARITY_TOL)    # e.g. rtol=1e-9
```

- **Pro:** keeps the independent oracle *and* turns "assumed parity" into "tested
  parity." Formula drift now fails a fast unit test instead of silently skewing the
  benchmark. Pairs naturally with the convention table in `MODELS.md`.
- **Con:** one more test to maintain; tolerance must be chosen per model
  (FWHM↔σ and `fraction` conventions are the usual offenders). It does not, by
  itself, exercise the noise/initial-guess regime of a full fit.

### (c) Hybrid

Use (b) as the default data path **and** add an optional self-consistent mode (a)
behind a flag, used only for pure solver-timing or convergence studies where
kernel correctness is already established by (b).

- **Pro:** correctness coverage (independent oracle + parity test) for the normal
  case; clean, kernel-agnostic timing numbers when wanted.
- **Con:** two code paths to keep honest; results from the two modes must be
  labelled so they are never compared head-to-head.

### Recommendation

**Adopt (b): keep the Python reference kernel as the independent oracle and add a
formula-parity test asserting Python↔Rust agreement to a tight tolerance.** It is
the smallest change that fixes the actual defect (untested parity) without
sacrificing the independent-oracle property that gives the benchmark its
correctness-validating value. Option (a)'s self-consistency is a liability for a
correctness benchmark, not an asset; reach for the (c) hybrid only if a dedicated,
clearly-labelled solver-timing study needs kernel-agnostic data.

---

## 4. Benchmark fairness invariants (standing rules)

These are project rules from `CLAUDE.md` and the backend code. Treat them as
invariants; changing one without changing the others invalidates cross-backend
comparisons.

1. **Same algorithm, same tolerance.** All three backends use Levenberg–Marquardt
   with the same stopping tolerance, `tol=1e-3`, matching the scipy/lmfit default.
   - lmfit uses `method="least_squares"` (`backends/_lmfit.py`), i.e. the
     scipy least-squares default tolerance.
   - jax sets `rtol=1e-3`, `atol=1e-3` explicitly, annotated "matches scipy/lmfit
     tol default" (`backends/_jax.py`).
   - spectrafit runs the Rust `lm` solver via `FitOptions`
     (`backends/_spectrafit.py`); the LM tolerance plumbs through
     `crates/spectrafit-solver/src/lm.rs`.
2. **Do not tighten JAX tolerance unilaterally.** Tightening one backend's
   tolerance makes it do more work per fit and renders timing comparisons unfair.
   If a tolerance must change, change it consistently across all three backends.
3. **Adding a model touches five places.** Per `CLAUDE.md`: a Python formula in
   `python/benchmark/models.py`; a `model_hint` value in the
   `CaseStructure.model` `Literal` in `backends/_shared.py`; an entry in
   `_MODEL_MAP` (or `is_supported() → False`) in `backends/_spectrafit.py`; a
   branch in `_build_lmfit_model()` in `backends/_lmfit.py`; and a branch in
   `_pre_timing_hook()` in `backends/_jax.py`. A model added to fewer than all five
   is silently absent or unfairly compared.

---

## 5. Reproducibility

### Run types

All commands are `poe` tasks (`pyproject.toml`) or `python -m benchmark.cli`
invocations (the `spc-bench` console script was removed in Option A packaging,
2026-06-20 — run the bench via `uv run poe benchmark` or
`uv run python -m benchmark.cli`).
Background variants use the `run_bg` dispatcher (`poe run_bg <task>` via
`scripts/run_pytest_bg.sh`). Rep counts are CLI options; defaults live in
`python/benchmark/cli.py`.

| Run type | Command | Reps / sweep |
|---|---|---|
| Default benchmark | `poe benchmark` / `uv run python -m benchmark.cli run` | 5 reps, full catalog (`--reps 5 --mc 20`) |
| Quick (local iteration) | `poe benchmark_quick` / `uv run python -m benchmark.cli run --reps 3 --mc 6` | 3 reps |
| Gate | `poe benchmark_gate` / `uv run python -m benchmark.cli gate` | reads latest manifest |
| Reps sweep | `uv run python -m benchmark.cli sweep --tiers 1,3,5,10,20` | arbitrary comma-separated rep ladder |

The `sweep` sub-command runs the bench at each rep budget in sequence and emits a
variance-vs-N stability table; there is no fixed Fibonacci sweep or pre-defined cold-vs-hot
poe task. Cold/hot amortization is computed analytically in `engine._warmup()` from a
single cold-start sample and the warm median, then surfaced as a `Warmup` block in the
`BenchReport` contract (see `python/benchmark/contract.py`).

### Where artifacts land

Each run is exported to an isolated per-run folder so results are never overwritten:

```
.spectrafit_reports/benchmark/<YYYY-MM-DD>_run_NNN/results.{json,html,pdf}
```

The run-directory naming and allocation are implemented in
`python/benchmark/reports.py` (run id pattern `^(\d{4}-\d{2}-\d{2})_run_(\d{3,})$`).
The newest run can be resolved programmatically via the
`mcp__spectrafit-reports__latest_results` MCP tool or
`python/oracles/reports.py:latest_results()`.

### Post-run analysis

After any `pytest tests/quick_validation/` run, post-analysis is mandatory
(`CLAUDE.md`): find the newest `results.json` under
`.spectrafit_reports/quick-validation/` and run
`PYTHONPATH=python uv run python -m oracles.post_analysis <path>`.
Scope the `find` to the `quick-validation` subtree, because benchmark runs also
write `results.json` under `.spectrafit_reports/benchmark/<date>_run_NNN/`.
