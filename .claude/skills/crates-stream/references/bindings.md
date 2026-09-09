# Bindings reference — PyO3 ABI, JSON boundary, ImportError

Self-contained essentials for the PyO3 binding surface. Historical
content lives in git history under `.claude/skills/spectrafit-bindings/`.

## Failure modes this reference covers

- `ImportError` / `ModuleNotFoundError` when calling `import
  spectrafit_core` after a fresh build.
- PyO3 panics surfaced as `pyo3::PanicException`.
- JSON boundary mismatches — the Rust side returns a serde value the
  Python side fails to validate as `BenchReport`.
- Maturin build issues (stale wheel, wrong Python, mismatched ABI).

## crates-stream contract additions

1. **Locate first** — `Grep __pyo3` and `Grep "fn fit\b|fn fit_fast"` to
   find the binding entry points (`fit`, `fit_fast`) and every call site
   before touching them.
2. **Wire = pyo3 ABI**. The crates → python inter-stream wire's proof:
   import the built extension in a one-line script, call `fit_fast` with
   a fixture payload, assert `BenchReport.model_validate(...)` accepts
   the return shape.
3. **Hooks that will fire on binding work**: `pre-merge-pyO3.sh` (gate)
   and (indirectly) `enforce-modeltype-parity.sh` when the binding adds
   a new model variant.

## Quick paths

- ABI entrypoints: `crates/spectrafit-core/src/lib.rs` (look for the
  `#[pymodule]` and `#[pyfunction]` symbols via Grep).
- Build: `maturin develop --release` (do not edit `pyproject.toml`
  build-system block lightly).
- ImportError diagnosis: `uv run python -c "import spectrafit_core;
  print(spectrafit_core.__file__)"`; mismatched wheel/site-packages is
  the #1 cause.

## Stuck-mode entry

A binding wire that reopens often signals a deeper ABI drift — escalate
to the curiosity sub-cycle (`Grep` for every reference to the function),
then reframe (is the binding the wrong shape?), then council
(is pyo3 the right abstraction layer?).
