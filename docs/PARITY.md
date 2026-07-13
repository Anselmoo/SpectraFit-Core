# Rust <-> Python Schema & API Parity

Audit of parity between the Rust serde structs in
`crates/spectrafit-types/src/types.rs` and the Python Pydantic models in
`python/spectrafit_core/` (`parameters.py`, `data.py`, `options.py`,
`result.py`, `models.py`, `graph.py`), plus the binding surface
`crates/spectrafit-core/src/lib.rs` <-> `python/spectrafit_core/_core.pyi`.

Enforced by `tests/parity/test_schema_parity.py`, which round-trips every model
through the real `spectrafit_core._core` boundary (Pydantic JSON in, serde JSON
out) and asserts field-for-field equality.

**Status (2026-06-01): no BREAKING drift.** All eight model pairs are
field-for-field aligned. The asymmetries below are intentional, working, and
covered by tests — none cause silent data loss.

## Schema Audit Report

**Scope:** `python/spectrafit_core/*.py` <-> `crates/spectrafit-types/src/types.rs`

### Parameter <-> ParameterSpec

| Field | Python (Pydantic) | Rust (serde) | Status |
|-------|-------------------|--------------|--------|
| value | `float` | `f64` | OK |
| min | `float = -inf` (null -> -inf) | `f64` (`deser_min`, `ser_bound`) | OK (inf<->null) |
| max | `float = +inf` (null -> +inf) | `f64` (`deser_max`, `ser_bound`) | OK (inf<->null) |
| vary | `bool = True` | `bool` | OK |
| expr | `str \| None = None` | `Option<String>` `#[serde(default)]` | OK |
| scale | `float \| None = None` | `Option<f64>` `#[serde(default)]` | OK |

### ParameterResult <-> ParameterResultSpec

`ParameterResult` extends `Parameter` with `name` and `stderr`.

| Field | Python | Rust | Status |
|-------|--------|------|--------|
| name | `str \| None = None` | `String` (always set by engine) | OK |
| value / vary / expr / scale | as Parameter | as Parameter | OK |
| min / max | `float` (inf) | `Option<f64>` (`ser_opt_bound` -> null for inf) | OK (inf<->null) |
| stderr | `float \| None = None` | `Option<f64>` `#[serde(default)]` | OK |

### FitGraph <-> FitGraphSpec / ModelNodeSpec / ExprEdge

| Field | Python | Rust | Status |
|-------|--------|------|--------|
| schema_version | `str = "0.1"` | `String` | OK |
| nodes | `list[ModelNodeSpec]` | `Vec<ModelNodeSpec>` | OK |
| expr_edges | `list[ExprEdge]` (default `[]`) | `Vec<ExprEdge>` `#[serde(default)]` | OK |
| node.id / model_type / parameters | matched | matched | OK |
| edge.target_node / target_param / expression | matched | matched | OK |

`ModelType` (Python `str`-enum) and `ModelTypeStr` (Rust `snake_case` enum) share
the same 11 wire values: `gaussian, lorentzian, voigt, constant, linear,
arctan_step, tanh_step, erfc_step, pseudo_voigt, fano, double_exponential`.

### MeasurementData <-> MeasurementSpec

| Field | Python | Rust | Status |
|-------|--------|------|--------|
| schema_version | `str = "0.1"` (always emitted) | `Option<String>` `#[serde(default)]` | OK (Rust accepts present-or-absent) |
| x | `list[list[float]]` (N x D) | `Vec<Vec<f64>>` | OK (boundary transposes for solver) |
| y | `list[float]` | `Vec<f64>` | OK |
| sigma | `list[float] \| None` | `Option<Vec<f64>>` `#[serde(default)]` | OK |
| label | `str \| None` | `Option<String>` `#[serde(default)]` | OK |

### FitOptions <-> FitOptionsSpec

| Field | Python | Rust | Status |
|-------|--------|------|--------|
| schema_version | `str = "0.1"` | `Option<String>` `#[serde(default)]` | OK |
| solver | `str = "lm"` | `String` | OK |
| max_iterations | `int = 200` | `u64` | OK |
| tolerance | `float = 1e-8` | `f64` | OK |

### FitResult <-> FitResultSpec / DatasetSlice <-> DatasetSliceSpec

All 19 `FitResult` fields and all 5 `DatasetSlice` fields match the Rust structs
one-for-one (verified by `test_fit_result_field_set_matches_rust` and
`test_dataset_slice_parity_for_multi_dataset_fit`). `parameters` accepts a
legacy `params` validation alias on the Python side (serialises as `parameters`,
which is what Rust emits).

## API-Surface Parity

**Rust capability set** (`crates/spectrafit-core/src/lib.rs`, declared in
`_core.pyi`): `fit`, `fit_arrays`, `fit_arrays_numpy`, `evaluate`,
`evaluate_components`.

**Python public API** (`spectrafit_core.__all__`): high-level `fit`, `fit_fast`,
`evaluate`, `evaluate_components`, plus `FitGraph.eval` / `FitGraph.eval_components`.

| Python | Rust binding used | Status |
|--------|-------------------|--------|
| `fit` | `fit_arrays` | OK |
| `fit_fast` | `fit_arrays_numpy` | OK |
| `evaluate` | `evaluate` | OK |
| `evaluate_components` | `evaluate_components` | OK |
| `FitGraph.eval` | `evaluate` | OK |
| `FitGraph.eval_components` | `evaluate_components` | OK |

No drift: every Rust capability is reachable from Python, and every Python entry
point maps onto a Rust capability. (`fit_arrays` is reached indirectly through
the high-level `fit`; it is not a separate public Python name, by design.)

## Intentional, non-breaking asymmetries (documented, not drift)

These are by design and covered by parity tests:

1. **±inf <-> null for bounds.** Rust serialises infinite bounds as JSON `null`
   (`ser_bound` / `ser_opt_bound`); Python serialises its `±inf` floats as `null`
   and parses `null` back to `±inf` (`_null_min_to_neginf` / `_null_max_to_posinf`).
   Round-trips losslessly.
2. **`schema_version` Optional on Rust input structs.** `MeasurementSpec` and
   `FitOptionsSpec` use `Option<String>` + `#[serde(default)]` so older payloads
   without the field still deserialise. Python always emits `"0.1"`. No loss.
3. **`params` validation alias.** `FitResult.parameters` accepts an incoming
   `params` alias for backward compatibility but always serialises as
   `parameters` (matching Rust output).
4. **`covariance` inner nullability.** Python types it as
   `list[list[float | None]] | None` (slightly wider than Rust
   `Option<Vec<Vec<f64>>>`). Rust never emits inner `null`, so this is a
   non-breaking superset on the Python side.
5. **`extra="forbid"`** on Python data models means any *future* Rust field added
   without a Python counterpart fails loudly on output parsing rather than being
   silently dropped — this is the trip-wire that keeps the round-trips honest.

## Checklist

- [x] Both sides reviewed in the same audit
- [x] Alias / rename parity confirmed (none required — names already match)
- [x] Round-trip tests present (`tests/parity/test_schema_parity.py`)
- [x] Optional parity verified (`Option<T>` <-> `T | None`)
- [x] API-surface parity verified
- [ ] No outstanding BREAKING drift (nothing to track)

There are currently **no** `@pytest.mark.xfail` parity cases because no
unfixed drift exists. If future drift is introduced, add an `xfail` test here
with `reason="parity drift: <field>; see docs/PARITY.md"` and a checklist row
above.
