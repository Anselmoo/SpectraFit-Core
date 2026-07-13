# API Stability Baseline — Rust Traits + Python Wheel Layer

**Source audits:** `docs/superpowers/audits/2026-06-10-rust-trait-stability.md`,
`docs/superpowers/audits/2026-06-10-python-wheel-layer-audit.md`
**Date established:** 2026-06-10

---

## Rust trait stability classification

| Trait | Crate | SemVer level | PyO3 surface |
|---|---|---|---|
| `Model` | spectrafit-models | **STABLE (wheel ABI)** | Indirect — `Box<dyn Model>` stored in the cdylib |
| `SubproblemStep` | spectrafit-trust-region | **INTERNAL** | None |
| `TrustRegionProblem` | spectrafit-trust-region | **INTERNAL** | None |

### `Model` trait governance rules
- Required methods: `eval`, `param_names`. All others have defaults.
- Supertraits: `Send + Sync` — part of the ABI contract; removing them is breaking.
- **NEVER without a major wheel bump:** rename `eval`, change `param_names` return type,
  remove `Send + Sync`, add a required method without a default.
- **Safe to add:** a method with a default implementation (e.g. `jacobian_condition_number`).
- 29 production implementors (27 peak-shape kernels + 2 test stubs).
- Adding a required method breaks all 29 implementors — always provide a default.

### `SubproblemStep` / `TrustRegionProblem` governance
- INTERNAL: all implementors are workspace-owned; can change freely within one PR.
- Candidates for `pub(crate)` demotion in a 6-month review (no external users confirmed).

---

## Python wheel-facing layer hot spots (2026-06-10)

10 `.py` files in `python/spectrafit_core/`; 65 functions; 47 public symbols in `__all__`.

**Critical (zen score 0 — Plan B2 target):** `fit.py`
- `fit` and `fit_fast` are 89/83 LOC, CC=15, nesting depth 4.
- ~85% code overlap (shared prologue: validate, normalize, n_dims guard, flatten arrays).
- Fix: extract `_prepare_arrays()` helper; both functions call it, then diverge only on the
  terminal `core.*` call. Eliminates ~105 LOC of duplication; brings CC ≤ 5.

**Secondary:** `__init__.py` — 47-entry `__all__` hoists 35 compose factory functions
to top-level (ZEN-STRICT-FENCES sev 7). Candidate for `spectrafit_core.compose.*` sub-namespace
(Plan B4). The 12 structural names that should remain at top-level:
`ComposeBuilder`, `compose`, `DatasetSlice`, `ExprEdge`, `FitGraph`, `FitOptions`,
`FitResult`, `GlobalFitGraph`, `MeasurementData`, `ModelNodeSpec`, `ModelType`,
`Parameter`, `ParameterResult` + `fit`, `fit_fast`, `evaluate`, `evaluate_components`.

**Clean files (no violations):** `compose.py`, `data.py`, `graph.py`, `models.py`,
`options.py`, `parameters.py`, `result.py`, `evaluate.py`.

## `_core.pyi` stub fidelity (2026-06-10)
All 5 public symbols match runtime exactly (name + parameter names + count).
No stale/missing declarations.
**Highest-severity drift:** `evaluate` stub docstring says "Returns JSON with best_fit array"
(implying a dict); runtime says "return a flat JSON array `[f64, ...]`". A caller reading
only the stub could write `json.loads(result)["best_fit"]` expecting a dict — the actual
return IS the flat array.
Fix: correct `_core.pyi` line 75; align all 5 summary lines with Rust-side wording.
