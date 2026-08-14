---
icon: lucide/git-branch
description: The two extension points — adding a peak/background model, and adding a solver family — with every touchpoint each one requires.
---

# Extending SpectraFit-Core

SpectraFit-Core has two extension points that contributors reach for most
often: **adding a model** (a new peak or background kernel) and **adding a
solver family** (a new optimisation algorithm). Both are deliberately
multi-crate changes. The crate-per-concern layout means a new solver family is
a new crate rather than a patch to an existing one, and the compile-time gates
described below mean a half-finished extension fails to build instead of
failing at run time in a user's fit.

This page lists every touchpoint. Skipping one is not a silent partial success
— it is a failed build or a red pre-commit hook, by design.

## Adding a model

A model kernel travels from the Rust core out to the Python surface and the
benchmark registry. All six steps belong in the **same commit**; the
schema-sync hook rejects a Rust-side change that leaves the Python side behind.

1. **Rust kernel** — implement the evaluation (and its analytic Jacobian) in
   `crates/spectrafit-models/`. Analytic Jacobians are the norm here, not an
   optimisation: the solvers consume them directly rather than
   finite-differencing.
2. **`ModelTypeStr`** — add the wire-string variant in
   `crates/spectrafit-types/src/types.rs`. Downstream hand-lists are derived
   from `ModelTypeStr::ALL` rather than repeated, so this is the single place
   the variant set is declared.
3. **`spectrafit-builder` gate** — `crates/spectrafit-builder/` is a
   compile-time exhaustiveness gate that nothing on the runtime path depends
   on. A variant that is not handled everywhere fails to compile (E0004) rather
   than reaching a user.
4. **Python `ModelType`** — mirror the variant in
   `python/spectrafit_core/models.py`. The `pre-merge-schema-sync` hook checks
   this against the Rust side; a mismatch blocks the commit.
5. **Benchmark registry** — register the shape once in
   `oracles.models.MODEL_REGISTRY`. Backends read the registry; none of them
   may keep a private map of their own.
6. **Case recipe** — add at least one benchmark case exercising the new kernel,
   so the model is covered by the cross-backend comparison rather than only by
   unit tests.

Document the kernel's formula in `docs/reference/models/index.md`. Note that
mathematical notation in Python docstrings is real LaTeX (`$\chi^2$`, `$\pm$`),
never a hand-typed Unicode approximation — and that any `Field(description=...)`
serialised into `BenchReport` is contract text, so changing one requires
`uv run poe contract_regen`.

## Adding a solver family

1. **New crate** — create `crates/spectrafit-<family>/`. Respect the dependency
   direction: the `pre-merge-dag` hook rejects a back-edge, so place code to
   satisfy the DAG rather than introducing one as a shortcut. Three of the
   existing families (`dogleg`, `newton-cg`, `levenberg-marquardt`) build on
   the shared `spectrafit-trust-region` core; `varpro` instead sits on
   `spectrafit-graph` and `spectrafit-models`. Reuse whichever fits, or depend
   only on `spectrafit-types` if neither does.
2. **`Solver` variant** — add the variant to the `Solver` enum in
   `crates/spectrafit-solver/src/dispatch.rs` and extend its string parser.
   Unrecognised solver strings are rejected rather than silently falling back
   to a default, so the parser arm is required, not optional.
3. **Routing** — decide whether `Solver::Auto` should ever select the new
   family. `Auto` currently routes to VarPro when the graph is separable,
   unconstrained and untied, and to the faer LM family otherwise. Extending
   `Auto` is a behaviour change for every existing user who did not name a
   solver explicitly; prefer opt-in by name first.
4. **Binding audit** — every new `#[pyfunction]` registered in
   `crates/spectrafit-core/src/lib.rs` and every new `Solver::` variant needs a
   one-line entry in `scripts/binding_audit_notes.toml`, followed by
   `uv run poe audit_bindings_regen`. `scripts/audit_bindings.py` enforces this
   in CI.
5. **Parity test** — add the family to the cross-implementation parity tests
   under `crates/spectrafit-solver/tests/`. A new solver that agrees with no
   existing one on a shared problem is a bug report, not a feature.

## Before you push

Run the loop for every stack your change touches — a model or solver change
usually touches at least Rust and Python. The Rust half is
`cargo fmt --check`, the workspace-wide `clippy` and `check` invocations listed
in [`CLAUDE.md`](https://github.com/Anselmoo/spectrafit-core/blob/main/CLAUDE.md),
then:

```bash
uv run --with maturin maturin develop --release   # Python won't see Rust changes without this
uv run poe lint_ci
uv run poe scenario_smoke                          # fast cross-stack check
uv run poe benchmark_gate                          # spectrafit-vs-lmfit regression gate
```

Rebuilding the extension is the step most often forgotten. A Rust-only test run
passes against changed Rust while the installed Python extension is still the
old build, so the Python suite silently tests stale code.

## Getting help

Open an issue at
[github.com/Anselmoo/spectrafit-core/issues](https://github.com/Anselmoo/spectrafit-core/issues).
For an extension you intend to contribute back, opening the issue *before*
writing the crate is worthwhile — the DAG and gate constraints above are easier
to design around than to retrofit.
