---
icon: lucide/puzzle
description: Implementing a new model's Rust kernel and wiring it into the canonical ModelTypeStr type so the compiler, solver, and Python bindings can see it.
tags:
  - PyO3
  - Models
  - Rust
---

# Adding a Model

This guide covers the part of adding a new spectrafit model that every
library contributor needs: implementing the Rust kernel and wiring it into
the canonical `ModelTypeStr` type so the rest of the codebase (compiler,
solver, Python bindings) can see it.

!!! warning
    Wiring the Rust kernel, `ModelTypeStr`, and the Python `ModelType` mirror
    makes the model usable — but it is **not optional** to stop there.
    `tests/parity/test_model_type_registry_bijection.py` fails CI if a new
    `ModelType` member isn't also registered in `oracles.models.MODEL_REGISTRY`
    (the exemption list is pinned to exactly two multi-dimensional
    showcases). Registering it in the internal benchmark registry (the
    Python-side oracle comparison against lmfit/JAX) is a separate, larger
    step — see [Adding a new benchmark model](../contributor-guide/benchmark-engine.md#adding-a-new-benchmark-model)
    — but skipping it is a red build, not a smaller/optional deliverable.

## The full chain, at a glance

Adding a model that's both usable and benchmarked spans three pages. This one
covers steps 1-3 in detail; the rest are one line each with a link to where
they're actually covered:

1. Implement the Rust kernel (`eval`, `param_names`) — [below](#1-implement-the-rust-kernel).
2. Register the wire type in the `model_manifest!` table (`ModelTypeStr`) — [below](#2-register-the-canonical-type-wire-the-exhaustiveness-gate).
3. Wire the `spectrafit-builder` exhaustiveness gate (two files) — [below](#2-register-the-canonical-type-wire-the-exhaustiveness-gate).
4. Mirror the variant in Python `ModelType` — [below](#mirror-the-variant-in-python).
5. Optionally override `Model::jacobian` for an analytical derivative — see
   [Extending SpectraFit-Core](../contributor-guide/extending.md#adding-a-model).
6. Register a `PeakModel` in the benchmark registry — see
   [Adding a new benchmark model](../contributor-guide/benchmark-engine.md#adding-a-new-benchmark-model).
7. Add a typed component spec and a `_peak()` dispatch arm in `oracles/cases.py`
   (same benchmark-engine section).
8. Exercise the model in a benchmark category (same section).
9. Wire jax support if you set `jax_supported=True` (same section).
10. Regenerate the contract if `bench_contract.py`/`contract.py` changed
    (same section).
11. Verify: Rust/numpy parity (`test_wheel_eval.py`) and the regression gate
    (`poe benchmark_gate`) (same section).
12. Document the formula in `docs/reference/models/index.md` — see
    [Extending SpectraFit-Core](../contributor-guide/extending.md#adding-a-model).
13. Run the pre-push loop for both stacks touched — see
    [Extending SpectraFit-Core](../contributor-guide/extending.md#before-you-push).

## 1. Implement the Rust kernel

Add `crates/spectrafit-models/src/<name>.rs` implementing the `Model`
trait (`crates/spectrafit-models/src/lib.rs`). Only two methods are
required — `eval` and `param_names` — everything else on the trait has a
working default:

```rust
use crate::Model;

/// Example skeleton — replace `MyModel`, the formula, and the parameter
/// names with your own.
///
/// Parameters (in order): `[a, b]`.
pub struct MyModel;

impl Model for MyModel {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, b) = (params[0], params[1]);
        a * x[0].powi(2) + b
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["a".into(), "b".into()]
    }
}
```

- `eval` — the forward model evaluation. Implementations index `x`/`params`
  by raw position and assume the caller already validated arity (kept
  branch-free on the hot path — see the trait's own doc comment for the
  panic contract).
- `param_names` — the canonical parameter names, in order.
- **Jacobian: free by default.** `Model::jacobian` ships a forward-difference
  finite-difference implementation (`h = 1e-7 * |params[i]|.max(1e-7)`) — you
  don't have to write one to get a working model. Override `jacobian`
  (and, for the hot path, `jacobian_into`) only when you want an analytical
  derivative for better performance/precision; `gaussian.rs` is a worked
  example of a kernel that does.

Wire the new module into `crates/spectrafit-models/src/lib.rs`:

- `pub mod <name>;`
- A `model_from_str` match arm that returns `Box::new(<Name>)`.

## 2. Register the canonical type + wire the exhaustiveness gate

Add one line to the `model_manifest!` table in
`crates/spectrafit-types/src/types.rs`, e.g.:

```rust
Gaussian => "gaussian",
```

This single table entry is enough — the macro generates the `ModelTypeStr`
enum variant, its `as_str()` match arm, `VARIANT_COUNT`, and the `ALL`
enumeration all from that one line. There is no separate hand-written
`as_str` match arm to add. The serde rename and the `as_str()` return value
must agree — this is pinned by the
`model_type_as_str_matches_serde_wire_for_every_variant` test. Callers such
as `spectrafit-graph::compiler` and `spectrafit-varpro` read `as_str()`
directly, so there's no per-crate duplicate table to keep in sync.

!!! warning

    A new `ModelTypeStr` variant also trips the **`spectrafit-builder`
    exhaustiveness gate** — a deliberate compile-time guard that lives in
    `#[cfg(test)]`, so `cargo build` will succeed but `cargo test` (and CI's
    `cargo test --workspace`) will fail with `E0004` until you wire it up. Two
    files need edits:

    - `crates/spectrafit-builder/src/lib.rs` — add the fluent `add_<name>()`
      method, an `ALL_MODELS` entry, and the new arm in both the exhaustive
      `match` and the `representatives` list.
    - `crates/spectrafit-builder/tests/builder_roundtrip.rs` — add the variant
      to the `available_models_matches_modeltypestr_parity_list` `expected`
      list, plus a `roundtrip_<name>` test.

    This gate is easy to miss because it's test-only — always run
    `cargo test -p spectrafit-builder` after adding a variant, even if
    `cargo build` was clean.

## Worked examples

The existing kernels `true_voigt` (Faddeeva), `skewed_gaussian`,
`exp_gaussian` (the exponentially-modified Gaussian, EMG), and
`doniach_sunjic` all went through this exact sequence — use one of them as
a template for the `Model` trait implementation and the `model_manifest!`
entry.

## Next steps

### Mirror the variant in Python

Once the Rust kernel and `ModelTypeStr` variant are wired, add the matching
member to the hand-written `ModelType` `StrEnum` in
`python/spectrafit_core/models.py` yourself — nothing generates or auto-syncs
it. Nothing blocks a plain `git commit` if you skip this: `pre-merge-schema-sync`
explicitly excludes `ModelType` from its checks, and
`.claude/hooks/enforce-modeltype-parity.sh` is a Claude-Code-only
`PostToolUse` hook that only warns, so it never fires for a human running
`git commit`. What actually catches a mismatch is
`tests/parity/test_schema_parity.py::test_model_type_enum_parity`, which
fails in CI (not at commit time) if the Python enum's values and the
Rust-exposed `ModelTypeStr::ALL` set diverge.

### Register it in the benchmark

With the Rust kernel, `ModelTypeStr`, and Python `ModelType` all wired, the
model is usable from Rust and Python — but making it available in the
internal benchmark registry (bench formula, case recipes, contract
regeneration) is **required**, not optional, per
`tests/parity/test_model_type_registry_bijection.py`. See
[Adding a new benchmark model](../contributor-guide/benchmark-engine.md#adding-a-new-benchmark-model)
for that sequence.
