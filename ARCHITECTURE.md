# ARCHITECTURE — spectrafit-core

## Overview

spectrafit-core is a high-performance numerical fitting framework. The computation
kernel is written in Rust and exposed to Python via pyo3/maturin. The Python
layer provides Pydantic schemas, a DAG composition interface, and an HTML
dashboard for result visualisation.

## Goals

1. Replace lmfit's runtime Python dispatch with compiled Rust model kernels.
2. Replace binary-tree operator-overloaded composition with an explicit DAG IR.
3. Replace per-iteration `asteval` expression evaluation with pre-compiled
   expression trees evaluated in Rust.
4. Provide **analytical Jacobians** for all built-in model types (no finite
   differences).
5. Support global fits with correct DOF via rayon parallel residual evaluation.

---

## Stack

| Layer             | Technology                              |
|-------------------|-----------------------------------------|
| Kernel language   | Rust 2021 edition                       |
| Solver            | levenberg-marquardt crate (LM)          |
| Linear algebra    | nalgebra                                |
| Parallelism       | rayon                                   |
| Python binding    | pyo3 + maturin                          |
| Python schemas    | Pydantic v2                             |
| Python version    | >=3.13                                  |
| Package manager   | uv                                      |
| Devboard          | matplotlib + Jinja2 (poe devboard)      |

---

## Directory Layout

```
spectrafit-core/
├── pyproject.toml             # maturin build backend + project metadata
├── Cargo.toml                 # Rust workspace manifest (11 member crates)
├── .python-version            # 3.13
├── ARCHITECTURE.md
├── MANIFEST
│
├── crates/                    # Rust workspace — 11 crates (see crates/README.md)
│   ├── spectrafit-types/      # Serde IR + ModelTypeStr (canonical wire strings)
│   ├── spectrafit-models/     # Model trait + kernels with analytical/FD Jacobians
│   ├── spectrafit-trust-region/         # faer-native trust-region core (Δ-radius)
│   ├── spectrafit-levenberg-marquardt/  # LM / TRF / geodesic on the core
│   ├── spectrafit-dogleg/     # Powell's dogleg on the core
│   ├── spectrafit-newton-cg/  # matrix-free Newton-CG (Steihaug–Toint) on the core
│   ├── spectrafit-varpro/     # variable-projection solver
│   ├── spectrafit-graph/      # DAG compiler: evaluate / evaluate_components / jacobian
│   ├── spectrafit-solver/     # strategy dispatch + post-fit stats (chi², AIC, BIC, cov)
│   ├── spectrafit-builder/    # typed Rust DSL for FitGraphSpec (+ exhaustiveness gate)
│   └── spectrafit-core/       # cdylib maturin target; pyo3 #[pymodule] _core
│
├── python/
│   ├── spectrafit_core/
│   │   ├── __init__.py        # Public API re-export
│   │   ├── _core.pyi          # Type stubs for Rust extension
│   │   ├── parameters.py      # Parameter, ParameterResult
│   │   ├── models.py          # ModelType enum, ModelNodeSpec
│   │   ├── graph.py           # ExprEdge, FitGraph, FitGraph.compile()
│   │   ├── data.py            # MeasurementData
│   │   ├── options.py         # FitOptions
│   │   ├── result.py          # FitResult
│   │   └── fit.py             # fit() public entry point
│   │
│   └── extras/                # Developer tools and benchmarks
│       ├── __init__.py
│       ├── bench/             # Benchmark suite (registry-driven, pydantic-first)
│       │   ├── cases.py       #   CategoryDef registry + CaseSpec/CaseFamily
│       │   ├── models.py      #   MODEL_REGISTRY (numpy parity oracle)
│       │   ├── backends/      #   spectrafit (subject) + lmfit, jax (oracles)
│       │   ├── engine.py      #   build_report: suite + per-case deep-dives, 2-D, time-resolved
│       │   ├── contract.py    #   frozen BenchReport (Pydantic) → web/ via OpenAPI
│       │   ├── api.py         #   FastAPI: GET /api/report
│       │   ├── reports.py     #   .spectrafit_reports/<category>/<date>_run_NNN/{results,manifest}.json
│       │   └── cli.py         #   `run` / `gate`
│       └── benchmark/         # legacy (superseded by bench/ — pending removal)
│
│   # web/  (repo root)        # Vite + React report UI; fetches /api/report; vitest suite
│
├── scripts/
│   └── devboard.py            # poe devboard — render FitResult JSON → HTML
│
└── tests/
    ├── test_models.py
    ├── test_graph.py
    ├── test_fit.py
    └── test_result.py
```

---

## Data Flow

```
Python
  FitGraph (Pydantic)   MeasurementData     FitOptions
       |                      |                  |
       +---- .model_dump_json() ----------------+
                     |
                JSON strings  (pyo3 call)
                     v
Rust
  serde_json::from_str  ->  FitGraphSpec / MeasurementSpec / FitOptionsSpec
       |
  CompiledGraph::compile(&spec)
       |  topological sort, param binding (Free/Fixed/Expr)
       |
  FitProblem { graph, datasets: Vec<DatasetSpec>, params: DVector }
       |
  LevenbergMarquardt::new().minimize(problem)
       |  iterate: residuals(), jacobian()
       |
  cov = (J^T J)^{-1} * (chi2 / DOF)
  chi2, reduced_chi2, DOF, AIC, BIC
       |
  FitResultSpec  ->  serde_json::to_string()
                     |  (pyo3 return)
                     v
Python
  FitResult.model_validate_json(result_json)
```

---

## Model Composition — DAG IR

Models are defined as a directed acyclic graph at the Python level, serialised
to JSON, and evaluated entirely in Rust.

### Nodes

Each node is a `ModelNodeSpec`: a typed model instance with named parameters.

```python
class ModelNodeSpec(BaseModel):
    id: str                               # unique within graph
    model_type: ModelType                 # Gaussian | Lorentzian | ...
    parameters: dict[str, Parameter]
```

### Edges

Edges encode parameter constraints across nodes (stored in v0.1 IR; Rust
evaluation deferred to v0.2):

```python
class ExprEdge(BaseModel):
    target_node: str
    target_param: str
    expression: str    # e.g. "0.5 * peak1.amplitude"
```

### Aggregation

Default: **sum** of all node outputs at each x point.

### Why not operator overloading (lmfit-style)?

lmfit's `model1 + model2` creates a binary tree evaluated recursively at
Python speed, allocating N temporary NumPy arrays per iteration. Our DAG is
compiled once to a Rust struct; evaluation is a single O(N_nodes * N_x) loop
with no Python round-trips.

---

## Parameter Model

```python
class Parameter(BaseModel):
    value: float                # initial value
    min: float = -inf
    max: float = inf
    vary: bool = True           # False → fixed constant
    expr: str | None = None     # constraint expression (v0.2); requires vary=True
    scale: float | None = None  # solver step-size hint; None → |value| or 1.0
```

`name` is the dict key in `ModelNodeSpec.parameters` — not duplicated as a field.

A Pydantic `model_validator` enforces: if `expr` is set then `vary` must be `True`.

Three binding kinds resolved at compile time:

| Kind    | vary  | expr | Behaviour                               |
|---------|-------|------|-----------------------------------------|
| Free    | True  | None | Element of the optimisation vector      |
| Fixed   | False | None | Constant; never updated                 |
| Expr    | True  | set  | Derived from expression (v0.2 only)     |

Bounds (min, max) are enforced by clamping inside `residuals()`.
`scale` is forwarded to the LM solver's `x_scale` vector for parameter pre-conditioning.

---

## Rust Model Kernels

```rust
pub trait Model: Send + Sync {
    /// x is a coordinate slice: len=1 for 1-D models, len=D for nD models.
    fn eval(&self, x: &[f64], params: &[f64]) -> f64;
    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64>;  // analytical
    fn param_names(&self) -> &'static [&'static str];
    fn n_dims(&self) -> usize { 1 }  // override for nD models
}
```

### Built-in models (v0.1)

| Model       | Formula                              | Params                          |
|-------------|--------------------------------------|---------------------------------|
| Gaussian    | A * exp(-(x-c)^2 / (2*sigma^2))     | amplitude, center, sigma        |
| Lorentzian  | A / (1 + ((x-c)/sigma)^2)           | amplitude, center, sigma        |
| Voigt       | eta*L + (1-eta)*G  (pseudo-Voigt)   | amplitude, center, sigma, frac  |
| Constant    | c                                    | c                               |
| Linear      | m*x + b                              | slope, intercept                |

---

## DAG Graph Engine (Rust)

```
CompiledGraph {
    nodes:        Vec<CompiledNode>,
    free_params:  Vec<(node_id, param_name)>,  // ordered optimisation vector
    free_init:    Vec<f64>,                     // initial values
    free_bounds:  Vec<(f64, f64)>,              // (min, max) per free param
}

CompiledNode {
    id:            String,
    model:         Box<dyn Model>,
    param_binding: Vec<ParamBinding>,  // one slot per model param
}

enum ParamBinding {
    Free(usize),    // index into free_params
    Fixed(f64),     // compile-time constant
    // Expr(ExprNode) -- v0.2
}
```

### evaluate(&graph, x_vals, free_params)

```
output[i] = 0.0
for each node n:
    p = resolve params via n.param_binding
    for each i, coord in x_vals:               // coord = &x_vals[i]  (len D)
        output[i] += n.model.eval(coord, &p)
```

### jacobian(&graph, x_vals, free_params)

```
jac[i][j] = 0.0
for each node n:
    p = resolve params
    node_jac = n.model.jacobian(&x_vals[i], &p)  // analytical, coord slice
    for each slot k:
        if binding == Free(j): jac[i][j] += node_jac[k]
```

---

## Solver — Levenberg-Marquardt

`FitProblem` implements `LeastSquaresProblem<f64, Dyn, Dyn>` from the
`levenberg-marquardt` crate.

Residual:   `r_i = (y_i - f(x_i)) / sigma_i`
Jacobian:   `dr_i/dp_j = -(df/dp_j) / sigma_i`

### Post-fit statistics

```
chi2          = sum(r_i^2)
DOF           = N_points - N_free
reduced_chi2  = chi2 / DOF
cov           = (J^T J)^{-1} * (chi2 / DOF)
stderr[j]     = sqrt(cov[j,j])
AIC           = chi2 + 2 * N_free
BIC           = chi2 + N_free * ln(N_points)
r_squared     = 1 - sum((y_i - f_i)^2) / sum((y_i - y_mean)^2)
```

For multi-dataset global fits: `DOF = sum_d(N_d) - N_free_shared`.

See **Multi-Dataset & Multi-Dimensional Fitting** below.

---

## Standalone Evaluation (No Fitting)

The framework is usable without the solver — a first-class path in both
Python and Rust.

### Python

```python
# Evaluate compiled graph at given parameters, no fitting
y_model: np.ndarray = graph.eval(params, data)

# Per-node component outputs
components: dict[str, np.ndarray] = graph.eval_components(params, data)
```

`FitGraph.eval()` serialises graph + params + data to JSON, calls the Rust
`evaluate` pyfunction, and returns a numpy array. No LM solver is invoked.

### Rust public API

Both functions are `pub` in `src/lib.rs` so that Rust consumers can use the
crate as an `rlib` dependency without Python:

```rust
// Forward-evaluate the graph; returns JSON array of f64
pub fn evaluate(
    graph_json: &str,
    params_json: &str,
    data_json:   &str,
) -> Result<String, CoreError>;

// Returns JSON object {node_id: [f64]} — one array per DAG node
pub fn evaluate_components(
    graph_json: &str,
    params_json: &str,
    data_json:   &str,
) -> Result<String, CoreError>;
```

Both are also registered as `#[pyfunction]` in the `_core` module so Python
callers reach the same compiled code paths.

---

## Multi-Dataset & Multi-Dimensional Fitting

### Multi-dimensional independent variables

The `Model` trait accepts `x: &[f64]` — a coordinate slice of length `D`.
For standard 1-D models `D = 1`; callers pass `&[x_i]`. nD models override
`n_dims()` and expect e.g. `&[x_i, t_i]` for a 2-D energy/temperature surface.

On the Python side `MeasurementData.x` is a numpy array of shape `(N,)` for
1-D or `(N, D)` for nD. Serialised to JSON as a flat `list[list[float]]`
(each inner list is one coordinate vector); 1-D is `[[x0], [x1], ...]`.

```python
class MeasurementData(BaseModel):
    x: list[list[float]]        # shape (N, D); D=1 for 1-D data
    y: list[float]              # shape (N,)
    sigma: list[float] | None   # shape (N,) or None → uniform weight
    label: str | None = None    # optional dataset identifier
```

### Multi-dataset global fitting

`fit()` accepts a single dataset or a list of datasets. All datasets share the
same `FitGraph` (and therefore the same free parameters). Residuals from all
datasets are concatenated before the LM solver sees them.

```python
# single dataset
result = fit(graph, data, options)

# global fit over multiple datasets
result = fit(graph, [data_A, data_B, data_C], options)
```

On the Rust side `FitProblem` holds a `Vec<DatasetSpec>` and rayon
parallel-iterates over them when computing residuals and the Jacobian:

```
FitProblem {
    graph:    CompiledGraph,
    datasets: Vec<DatasetSpec>,   // each has x: Vec<Vec<f64>>, y, weights
    params:   DVector<f64>,
}

residuals():
    datasets
        .par_iter()                          // rayon
        .flat_map(|ds| ds.residuals(&graph, &params))
        .collect()

DOF = sum_d(N_d) - N_free_shared
```

The `FitResult` is the same schema regardless of whether one or many datasets
were used; `best_fit` and `residuals` are the concatenated arrays in dataset
order.

---

## FitResult

```python
class ParameterResult(BaseModel):
    name: str
    value: float
    min: float
    max: float
    vary: bool
    expr: str | None
    stderr: float | None        # None if fit did not converge

class DatasetSlice(BaseModel):
    label: str | None           # from MeasurementData.label
    n_points: int
    best_fit: list[float]       # model output for this dataset
    residuals: list[float]      # (y - f) / sigma for this dataset
    chi2: float                 # partial chi2 contribution

class FitResult(BaseModel):
    parameters: dict[str, ParameterResult]
    covariance: list[list[float]] | None
    chi2: float
    reduced_chi2: float
    r_squared: float
    dof: int
    aic: float
    bic: float
    n_iter: int
    success: bool
    message: str
    best_fit: list[float]       # concatenated across all datasets
    residuals: list[float]      # concatenated across all datasets
    init_fit: list[float]       # model at initial parameter values
    components: dict[str, list[float]]   # node_id → best_fit per DAG node
    dataset_slices: list[DatasetSlice] | None  # None for single-dataset
```

---

## Devboard

`scripts/devboard.py` is a standalone script invoked via `poe devboard`.
It accepts a `FitResult` JSON file path, renders figures with matplotlib
(PNG, base64-embedded), and writes a self-contained HTML using an inline
Jinja2 template string. No `templates/` directory.

1. Data + best-fit overlay
2. Residuals subplot
3. Parameter table: name | value | stderr | min | max | vary
4. Statistics table: chi2 | reduced_chi2 | DOF | AIC | BIC | n_iter | converged

---

## Python / Rust Boundary

All data crosses the boundary as **JSON strings**:

- Python → Rust:  `pydantic_obj.model_dump_json()` passed as `&str` via pyo3
- Rust → Python:  `serde_json::to_string(&result)` returned as `String`

This keeps the pyo3 FFI layer trivial (no custom type conversions) and makes
the boundary independently testable with plain string I/O.

Future: replace JSON with MessagePack for large-dataset performance.

---

## Versioning

`FitGraph` and `FitResult` carry `schema_version: str = "0.1"`. Breaking
schema changes bump the minor version. Unknown fields are silently ignored
(Pydantic `model_config = ConfigDict(extra="ignore")`).

---

## Out of Scope (v0.1)

| Feature                         | Notes                                   |
|---------------------------------|-----------------------------------------|
| Confidence interval profiling   | Needs profile-likelihood / MCMC         |
| Plugin / custom model registry  | Needs safe Rust FFI plugin loader       |
| Full covariance matrix input    | Requires Cholesky weight transform      |
| Energy-axis unit metadata       | Orthogonal to fitting logic             |
| ExprEdge Rust evaluation        | Needs safe expression parser            |
| Benchmark scripts               | Out of scope — this is a numerical framework, not a benchmark suite |

---

## Benchmark Engine + Report (`python/benchmark`)

The benchmark suite is **registry-driven and pydantic-first**, emitting a frozen JSON
contract consumed by a Vite + React UI. There is no Jinja2/HTML artifact — one data flow:
**benchmark run → results.json → FastAPI → React**.

### Module structure

```
python/oracles/        # (was python/benchmark/ — merged F13)
├── cases.py     # CategoryDef registry + CaseSpec/CaseFamily + build_catalog/materialize
├── models.py    # MODEL_REGISTRY — numpy formulas (the parity oracle for the Rust kernels)
├── backends/    # spectrafit (the SUBJECT) + lmfit, jax/optimistix (cross-check oracles)
├── engine.py    # build_report: run_suite (all 139) + run_featured (deep-dive every case);
│                #   _multidim() fits a 2-D map with the native gaussian2d kernel (real subject);
│                #   _time_resolved() runs a GlobalFitGraph joint multi-dataset fit
├── metrics.py   # timing / accuracy / ECDF / spread / pull statistics
├── synth.py     # deterministic synthetic BenchReport (test fixture; never served)
├── contract.py  # the FROZEN BenchReport contract (Pydantic) — single source of truth
├── api.py       # FastAPI: GET /api/report (latest), /api/runs, /api/report/{run_id}
├── reports.py   # run-centric output: .spectrafit_reports/<category>/<date>_run_NNN/
└── cli.py       # `run` (write results.json + manifest.json) · `gate` (regression gate)
```

### Contract → UI

`contract.py` is the single source of truth. The FastAPI app publishes its OpenAPI schema;
`web/src/openapi.gen.ts` is generated from it (`npm run contract`) and `web/src/contract.ts`
re-exports the view types — so the React views never drift from the Python models. The web
app (`web/`, Vite + React) fetches `/api/report` at boot and renders 5 views — **Overview**
(default hero: all-backend head-to-head with co-winner ties, suite distributions,
initial→best recovery ±σ, and the 2-D map + time-resolved showcases) / Dashboard / Report /
Cockpit / Export — with no silent fallback and no hardcoded backend ids. A `vitest` suite
(`web/src/__tests__/*`) renders every view from fixtures without a browser.

### Run & gate

`uv run poe benchmark` writes `results.json` + `manifest.json` into a fresh run dir;
`uv run poe serve` serves the latest over FastAPI; `python -m oracles.cli gate` fails if
the geomean speedup vs lmfit drops below 1× or max |Δr²| (LM-family) exceeds 1e-3.
`tests/test_bench_invariants.py` proves the JSON is real (every category deep-dived, analyzed
set multiple + unique, per-case plots distinct, all-finite) before the UI consumes it.

> Adding a model/case is a multi-crate change — see `CLAUDE.md` → "Adding a New Benchmark Model".
