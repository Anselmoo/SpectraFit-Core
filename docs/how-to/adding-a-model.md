# Adding a Model

This guide covers the part of adding a new spectrafit model that every
library contributor needs: implementing the Rust kernel and wiring it into
the canonical `ModelTypeStr` type so the rest of the codebase (compiler,
solver, Python bindings) can see it.

!!! note
    Adding a model to the project's internal benchmark registry (the
    Python-side oracle comparison against lmfit/JAX) is a separate step,
    documented in `CLAUDE.md`'s "Adding a New Benchmark Model" — follow that
    if you also need your model to show up in the benchmark dashboard.

## 1. Implement the Rust kernel

Add `crates/spectrafit-models/src/<name>.rs` implementing the `Model`
trait:

- `eval` — the forward model evaluation.
- `param_names` — the canonical parameter names, in order.
- A finite-difference (FD) Jacobian.

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
`exp_gaussian` (EMG), and `doniach_sunjic` all went through this exact
sequence — use one of them as a template for the `Model` trait
implementation and the `model_manifest!` entry.

## What's next

Once the Rust kernel and `ModelTypeStr` variant are wired, the model is
usable from Rust and visible to the Python `ModelType` enum via the
existing parity hook. Making it available in the internal benchmark
registry (bench formula, case recipes, contract regeneration) is a
separate, benchmark-engine-specific process — see `CLAUDE.md`'s "Adding a
New Benchmark Model" for that sequence if you need it.
