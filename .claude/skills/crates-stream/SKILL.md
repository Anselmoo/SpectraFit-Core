---
name: crates-stream
description: |
  Conductor for the Rust crates/ stream. Diagnoses + fixes kernels, solvers,
  workspace layout, PyO3 binding surface, and any other code under crates/.
  Absorbs spectrafit-solver, spectrafit-bindings, spectrafit-scaffold, and
  rust-model-scaffolder — their specialist content lives in references/.
  Use when a task touches Rust kernels, the LM/TRF/dogleg/Newton-CG solver
  family, the ModelTypeStr enum, the pyo3 ABI, or the crate workspace.
  Also when the user pastes Rust or PyO3/maturin code and asks "is this
  idiomatic?", "review this Rust", or "check my PyO3 code".
  Composes with superpowers:test-driven-development and
  superpowers:verification-before-completion. Serena-first.
license: MIT
---

# crates-stream

The single entry point for any Rust-side work in spectrafit-core. Reads
`.claude/skills/INDEX.yaml § crates-stream` for its anchor slice, then
dispatches to a `references/` sub-document for the specialist matter.

## Anchors (load these into context)

**CLAUDE.md sections** (read these before acting):
- *Adding a New Benchmark Model* — the six-step sequence the kernel + ABI must follow.
- *Code Conventions (pydantic-first)* — even Rust touches the contract; the serde renames must match Pydantic field names.

**Hooks that will fire** (respect their contract):
- `cargo-check-on-rust-edit.sh` — PostToolUse on `.rs` edits; runs `cargo check`. A red cargo means stop.
- `enforce-modeltype-parity.sh` — warns when `ModelTypeStr` and Python `ModelType` drift.
- `pre-merge-pyO3.sh` — pre-merge gate that the ABI compiled.
- `enforce-perf-accuracy.sh` — performance/accuracy gate (when present).

## Serena first (non-negotiable)

The first action on any code-touching task **MUST** be a serena MCP call,
not a Grep:

```
mcp__serena__get_symbols_overview  → workspace-level orientation
mcp__serena__find_symbol           → locate a Rust function / struct / impl
mcp__serena__find_referencing_symbols → who calls / uses this
mcp__serena__replace_symbol_body   → swap a symbol body in place
```

The `enforce-serena-first.sh` hook will warn (tier 1) or block (tier 2) on
`Grep` patterns shaped like `fn …`, `struct …`, `impl …`. If the grep is
genuinely *not* a symbol search (e.g. log line, error string, doc text),
proceed with grep — the hook only flags symbol-shaped patterns.

## Decision: which sub-document?

Read the corresponding `references/*.md` for the specialist content:

| Subject of the task | Reference |
|---------------------|-----------|
| Solver math, LM / TRF / dogleg / IRLS / Newton-CG, faer parity, regime selection | `references/solver.md` |
| PyO3 binding surface, `fit` / `fit_fast` ABI, JSON boundary, ImportError | `references/bindings.md` |
| Workspace layout, Cargo.toml plumbing, new crate creation, CI scaffold | `references/scaffold.md` |
| New model kernel (Gaussian-class, Lorentzian-class, Voigt, custom) — including the FD Jacobian and the cross-crate `ModelTypeStr` plumbing | `references/rust-models.md` |
| "Is this idiomatic?" / Rust/PyO3 idiom review, ownership/safety/FFI, before/after rewrites | `references/rustonicon.md` |

These references **absorb the prior** `spectrafit-solver`, `spectrafit-bindings`,
`spectrafit-scaffold`, and `rust-model-scaffolder` skills. The original
SKILL.md files remain for one transition cycle as redirect stubs.

## Composes with (call these in order)

1. **Before** touching code: `superpowers:test-driven-development` — write
   the failing test first.
2. **While** fixing: this skill's reference sub-document for the domain
   matter, with serena driving symbol-level edits.
3. **After** the fix: `superpowers:verification-before-completion` — run
   the verification commands and confirm output before claiming done.
4. **If you get stuck**: see `andon-loop/references/stuck-mode.md` — the
   tiered escape ladder (curiosity → reframe+spike → council).

## Three-pillar reporting

When closing a crates-stream cycle, report against the three pillars from
the conductor:

- **PERF**: name the benchmark case(s) touched; quote
  `manifest.geomean_speedup_vs_baseline` if a benchmark ran.
- **RIGOR**: name the parity oracle exercised (e.g. `lm` vs `lm-legacy`
  in `crates/spectrafit-solver/tests/parity.rs`); state `max |Δr²|`.
- **PRESENTATION**: if a kernel touched a contract surface that flows to
  the web (a new field in a serde struct), name the web panel that
  consumes it — otherwise N/A.

Pillars are reports in tier 1. In `harden` intent they become gates.

## Tier-1 status

This SKILL.md is the conductor scaffold. The `references/*.md` files
currently link back to the original specialist SKILL.md files; tier 2
will move the specialist body content into the references and convert
the originals into redirect stubs. The anchor contract (CLAUDE.md
sections + hooks + serena-first) is enforced **now**.
