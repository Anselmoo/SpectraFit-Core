# crates — spectrafit-core workspace

Each crate has a single responsibility. The dependency chain runs strictly downward.

The workspace is **11 crates**. Foundations (`types`, `models`) and the
faer-native `trust-region` core sit at the bottom; the four solver-method crates
build on the core; `graph`/`solver`/`builder` compose them; `core` is the PyO3
`cdylib` at the top.

| Crate | Path | Purpose |
|---|---|---|
| `spectrafit-types` | `crates/spectrafit-types` | Serde IR types mirroring the Python schemas; `ModelTypeStr` (canonical wire strings via `as_str()`); `CoreError` |
| `spectrafit-models` | `crates/spectrafit-models` | `Model` trait + the full 34-kernel catalog (Gaussian … `power_law_offset`, `mgh09_rational` — the authoritative list is `model_manifest!` in `spectrafit-types`) with analytical/FD Jacobians; `model_from_str`, `all_model_types()` |
| `spectrafit-trust-region` | `crates/spectrafit-trust-region` | faer-native trust-region core (Δ-radius framework) shared by the LM/TRF/dogleg/geodesic/Newton-CG solvers; per-iteration `Report` (cost/grad/θ history) |
| `spectrafit-levenberg-marquardt` | `crates/spectrafit-levenberg-marquardt` | Levenberg–Marquardt family (LM / TRF / geodesic) on the trust-region core |
| `spectrafit-dogleg` | `crates/spectrafit-dogleg` | Powell's dogleg trust-region method on the core |
| `spectrafit-newton-cg` | `crates/spectrafit-newton-cg` | Matrix-free Newton-CG (Steihaug–Toint truncated CG) trust-region method on the core |
| `spectrafit-varpro` | `crates/spectrafit-varpro` | Variable-projection (VarPro) solver |
| `spectrafit-graph` | `crates/spectrafit-graph` | DAG compiler (topo sort, cycle detection, `ParamBinding`); `evaluate`, `evaluate_components`, `jacobian` |
| `spectrafit-solver` | `crates/spectrafit-solver` | Strategy dispatch (`lm` = faer default, `lm-legacy`, `trf`, `irls`, `global`/DE, `varpro`, `geodesic`); post-fit statistics (chi², AIC, BIC, covariance) |
| `spectrafit-builder` | `crates/spectrafit-builder` | Typed Rust DSL for building a `FitGraphSpec` without hand-writing JSON; a `#[cfg(test)]` exhaustiveness gate forces every new `ModelTypeStr` variant to be wired |
| `spectrafit-core` | `crates/spectrafit-core` | `cdylib` maturin target; pyo3 `#[pyfunction]` `fit` / `fit_arrays` / `fit_arrays_numpy` / `evaluate` / `evaluate_components` / `model_type_wire_strings`; `#[pymodule] _core` |

## Dependency graph

```
spectrafit-types ─────────────┐
       ↑                       │
spectrafit-models ──────┐      │
       ↑                │      │
spectrafit-trust-region │      │
   ↑    ↑    ↑    ↑      │      │
  LM  dogleg newton-cg (varpro)│      (LM = spectrafit-levenberg-marquardt)
   └────┴────┴────┴─────→ spectrafit-solver ← spectrafit-graph
                                  ↑                  ↑
                          spectrafit-builder   (types)
                                  ↑
                          spectrafit-core  (cdylib → _core.so)
```

## Build commands

```bash
# Check all crates
cargo check --workspace

# Run all Rust unit tests
PYO3_PYTHON="$(uv run python -c 'import sys; print(sys.executable)')" \
  cargo test --workspace --lib

# Build and install the Python extension
uv run maturin develop

# Full Python test suite
PYTHONPATH=python uv run pytest -q tests/
```
