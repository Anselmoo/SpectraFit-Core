# Rust models reference — adding a new spectroscopic model kernel

Self-contained essentials for adding a new spectroscopic model.
Historical scaffolder content lives in git history under
`.claude/skills/rust-model-scaffolder/`.

## Scope

Generate the standardized boilerplate for a new model kernel under
`crates/spectrafit-models/src/<name>.rs`:

- the `Model` trait impl (`eval`, `param_names`, `jacobian` — finite
  differences ok if no analytical form, but document the choice);
- the `model_from_str` arm in `lib.rs` returning `Box::new(<Name>)`;
- tests comparing the kernel against a known analytical reference at
  representative parameter sets.

## crates-stream contract additions

This is the canonical multi-crate change. It is **not** "one record" —
follow the 6-step sequence from `CLAUDE.md § Adding a New Benchmark
Model`:

1. **Rust kernel** — `crates/spectrafit-models/src/<name>.rs` + the
   `model_from_str` arm in `lib.rs`.
2. **ModelTypeStr variant + canonical string** —
   `crates/spectrafit-types/src/types.rs`, both the enum variant AND the
   `as_str()` match arm. The serde rename and `as_str()` must agree
   (the `model_type_as_str_matches_serde_wire_for_every_variant` test
   pins this).
3. **Python `ModelType`** — `python/spectrafit_core/models.py` member
   with the same value. The `enforce-modeltype-parity.sh` hook will
   warn on drift.
4. **Bench model** — `register_model(...)` in `python/oracles/models.py`.
   *(This step crosses into the `python-stream` skill — in tri-stream
   mode, the python sub-loop handles it.)*
5. **Case recipe** — `CaseSpec`/`CaseFamily` in `python/oracles/cases.py`.
   *(python-stream.)*
6. **Regenerate contract** if `contract.py` changed (python-stream).

Steps 1–3 stay in `crates-stream`; 4–6 hand off via the crates↔python
inter-stream wire.

## Serena-first recipes

- Locating the existing model trait: `mcp__serena__find_symbol Model`
  in `crates/spectrafit-models/src/lib.rs`.
- Locating the ModelTypeStr enum:
  `mcp__serena__find_symbol ModelTypeStr` in `crates/spectrafit-types/`.
- Finding all callers of `as_str()` before renaming:
  `mcp__serena__find_referencing_symbols ModelTypeStr::as_str`.

## Stuck-mode entry

A reopened `ModelTypeStr` wire usually means serde rename vs `as_str()`
got out of sync — curiosity sub-cycle on
`mcp__serena__find_referencing_symbols ModelTypeStr` finds the gap fast.
