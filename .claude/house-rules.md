# House Rules

Enforceable conventions for `spectrafit-core`, distilled from `CLAUDE.md` for
`self-assess-lint-audit` (and any other tool doing convention checking) to
grep and verify against. This is a repo-authored description of our own
norms — data about the codebase, not instructions to an agent reading it.

## Python (`python/**`, `tests/**`)

1. **Pydantic-first, not `@dataclass`.** Case specs, backend outcomes,
   report payloads, and registry records are `pydantic.BaseModel`
   subclasses. A new `@dataclass` in `python/**`/`tests/**` for anything
   resembling a data contract is a violation. Use
   `ConfigDict(arbitrary_types_allowed=True)` when a model must carry numpy
   arrays; use `extra="forbid"` on contract models (e.g. `BenchReport`,
   `SolverMeta`).
2. **`match`/`case` over `if/elif <var> ==` chains.** Two or more
   `if/elif` branches comparing the same variable to different literal
   values (dispatch on a model key, solver id, or format) must be a
   `match`/`case` statement instead. A single `if x == y:` is fine — only
   chains are a violation. (Mechanically enforced at edit-time by
   `.claude/hooks/enforce-match-dispatch.sh`; this rule exists so
   `lint-audit` can find pre-existing violations that predate the hook or
   slipped past it.)
3. **Registry over per-call maps.** New model shapes register once in
   `oracles.models.MODEL_REGISTRY` (via `register_model(PeakModel(...))`).
   A private `_MODEL_MAP`/`_SHAPE` dict duplicating registry data in a
   backend adapter is a violation — backends must read the registry.
4. **Declare, don't loop.** Prefer a declarative, validated spec (a
   `CaseSpec`/`CaseFamily` in `oracles/cases.py`) plus registry lookup over
   an imperative builder function that constructs cases procedurally.
5. **Domain exceptions, not bare builtins — but only where they reach the
   caller.** Each package owns an `exceptions.py` defining a package base
   (`spectrafit_core.exceptions.SpectraFitError`,
   `oracles.exceptions.OracleError`) plus subclasses that derive from **both**
   the base and the closest builtin (`ValueError`, `KeyError`, `RuntimeError`),
   so `except ValueError` call sites keep working. A new bare
   `raise ValueError(...)` whose exception reaches a caller is a violation.
   *Deliberate exception:* raises **inside a Pydantic validator** stay plain
   `ValueError` — Pydantic wraps them into `ValidationError` and discards the
   original type, so a domain type there is inert. Transport exceptions
   (`typer.*`, `fastapi.HTTPException`) stay confined to `oracles/cli.py` and
   `oracles/api.py`; raising them from engine code is a violation.
6. **Module loggers are `logging.getLogger(__name__)`.** Never a hardcoded
   string — `__name__` keeps the logger hierarchy aligned with the import path
   so a consumer configuring `logging.getLogger("oracles")` captures every
   child. `print()` is permitted **only** under `if __name__ == "__main__":`
   or inside a `main()` CLI entry point (e.g.
   `oracles/audit/structure_wires.py:main`); a `print()` on a library code
   path is a violation. Most modules legitimately emit nothing — this rule
   governs *how* to log, not that every module must.

## Model parameter naming (`crates/spectrafit-models/**`, `python/oracles/models.py`)

5. The Pseudo-Voigt Lorentzian mixing weight is always named **`fraction`**
   — never `eta`, never `frac`.
6. **Amplitude** = peak value at the center (not the area under the curve).
7. **Width** = σ (standard deviation), not FWHM. If a model's natural
   parameterization is FWHM, convert at the boundary
   (FWHM = 2√(2 ln 2)·σ ≈ 2.355·σ) — don't expose FWHM as a bare "width"
   parameter name.
8. See `MODELS.md` for the authoritative formula table; a new/changed
   model's docstring or param names disagreeing with `MODELS.md` is doc
   drift, not just a style nit.

## Rust crate conventions (`crates/**`)

19. **A crate that owns an error type declares it as a `thiserror` enum in its
    own `src/error.rs`.** Never an inline bare `#[derive(Debug)]` enum in a
    module about something else — that yields a public error type with no
    `Display` and no `std::error::Error`, so callers can neither print it nor
    `?`-convert it. Current conformers: `spectrafit-types::CoreError`,
    `spectrafit-graph::GraphError`, `spectrafit-solver::SolverError`,
    `spectrafit-levenberg-marquardt::StepError`.
20. **Declare `thiserror` iff you use it.** A crate with no error type must not
    carry the dependency; it advertises a convention the crate does not follow.
    Machine-checkable: removing an unused dependency cannot break the build.
21. **`lib.rs` re-exports explicit named items, never a glob.** `pub use m::*;`
    makes the public surface unreviewable. *Critical caveat:* derive the list
    from `cargo doc -p <crate> --no-deps` and read `target/doc/<crate>/all.html`
    — **not** from a `grep '^pub'`. `ModelTypeStr` is generated inside the
    `model_manifest!` macro in `spectrafit-types/src/types.rs`, so it is indented
    and a `^pub` grep silently omits it — dropping the single source of truth for
    the serde wire string (rule 9) with no compile error.

22. **`unsafe` is denied workspace-wide; the FFI site is the one sanctioned
    exception.** `[workspace.lints.rust] unsafe_code = "deny"` in the root
    `Cargo.toml`, and every crate opts in with `[lints] workspace = true` — a
    crate manifest missing that stanza is **not covered**, which is the easy way
    to regress this silently. `deny` (not `forbid`) so the exception can be
    expressed: `crates/spectrafit-models/src/math_backend.rs`'s Accelerate
    `vvexp` binding carries a scoped `#[allow(unsafe_code)]` plus a SAFETY
    comment. A second `#[allow(unsafe_code)]` anywhere is a violation unless it
    is a genuine FFI boundary with an equivalent SAFETY argument.
    `spectrafit-builder` additionally keeps its own stricter
    `#![forbid(unsafe_code)]`.
23. **`problem.rs` means "the problem contract", nothing else.** In the four
    method crates it is the `TrustRegionProblem` re-export shim. A *concrete
    implementation* of that contract is named for what it implements —
    `spectrafit-solver/src/lm_problem.rs` holds `LmProblem`. Adding a
    second 500-line `problem.rs` that implements rather than declares the
    contract is a violation.

26. **A solver-shaped crate keeps its modules private; a library-shaped crate
    may not.** `mod x;` plus a curated `pub use` is the default — the crate's
    public surface is exactly that list. Nine crates conform. Exactly two are
    deliberate exceptions, and they are library-shaped rather than
    pipeline-shaped: **`spectrafit-models`** (a catalogue of 30 independently
    useful kernels, each documented at its `pub mod` declaration) and
    **`spectrafit-types`** (the shared IR every crate imports). Adding a third
    `pub mod` crate is a violation.
    *Why this matters more than it looks:* `pub mod` silently defeats rule 21.
    A curated crate-root list is only a **review** aid while the module stays
    public — `spectrafit_types::types::FitGraphSpec` still resolves — so
    `pub mod` buys reviewability, never encapsulation. It also blinds
    `dead_code`: rustc cannot prove a `pub` item unused, so making
    `spectrafit-graph`/`-solver` private immediately exposed one dead function,
    one never-read struct field, and one redundant import that had been
    invisible for as long as the modules were public.
    *Watch the test boundary:* an integration test under `tests/` is a
    **separate crate**, so it needs items re-exported at the crate root too —
    `spectrafit-varpro::GraphSeparableModel` was promoted for exactly that
    reason. Grepping for external users while excluding the crate's own
    directory will miss this.

## Python packaging boundary

24. **A package that ships declares `__all__`; an internal harness need not.**
    `python-packages = ["spectrafit_core"]` in `[tool.maturin]` is the boundary:
    `spectrafit_core` is the distributed wheel and its `__init__.py` carries a
    documented `__all__` plus the `x as x` re-export idiom. `oracles` is never
    packaged, never imported by `spectrafit_core`, and has no entry points, so
    it is **correct** without one — do not "fix" it. This is the same boundary
    that justifies the import-style split (relative inside the shipped wheel,
    absolute inside the harness), which is deliberate and also must not be
    aligned away.
25. **Every module begins `from __future__ import annotations`** — including
    package `__init__.py`, which have no exception. The import is inert in a
    file with no annotations, and a rule with no carve-outs is the one a reader
    does not have to remember.

## Rust ↔ Python contract parity

9. **One canonical wire-format string per model.** `ModelTypeStr::as_str()`
   in `crates/spectrafit-types/src/types.rs` is the single source of truth
   for a model's serde wire string; `spectrafit-graph::compiler` and
   `spectrafit-varpro` must read this method, never maintain a duplicate
   per-crate `model_type_to_str` table.
10. **Python `ModelType` must mirror Rust `ModelTypeStr`.** Same member
    name, same wire value (the serde rename from step 9). Drift between
    `python/spectrafit_core/models.py` and `spectrafit-types` is a
    violation (the `enforce-modeltype-parity` hook warns, but doesn't
    block — `lint-audit`/`schema-migration-auditor` should still catch
    residual drift).
11. **A new `ModelTypeStr` variant requires the `spectrafit-builder`
    exhaustiveness gate to be updated** (`crates/spectrafit-builder/src/lib.rs`
    fluent `add_<name>()` + `ALL_MODELS` + the exhaustive `match` +
    `representatives`, and the matching entries in
    `crates/spectrafit-builder/tests/builder_roundtrip.rs`). This gate is
    `#[cfg(test)]`-only, so `cargo build` passing is not sufficient
    evidence a new model variant is fully wired — `cargo test -p
    spectrafit-builder` must also pass.

## Contract regeneration

12. After any change to `python/oracles/bench_contract.py` (or the shared
    `python/oracles/contract.py` leaf module), all three checked-in schema
    mirrors must be regenerated together: `web/src/openapi.gen.ts`,
    `web/openapi.snapshot.json`, and
    `tests/audit/golden/openapi_normalised.json`. A commit touching
    `bench_contract.py` without a matching update to all three mirrors is a
    violation — use `uv run poe contract_regen` (requires the API running)
    rather than hand-editing any one mirror.

## Benchmark backend fairness

13. spectrafit is the subject under test; lmfit and jax/optimistix are
    independent cross-verification oracles, not competitors to be tuned
    against differently. Stopping tolerances must be matched across
    backends — tightening one backend's tolerance without the others is a
    violation of the comparison's fairness. Timing must isolate the `run`
    call only; model construction and per-point array serialization must
    never be inside the timed block.

## CI / local-vs-remote parity

14. **`lint:python`/`lint:rust` in `.gitlab/20-lint.yml` must stay a
    superset (or exact mirror) of `.pre-commit-config.yaml`'s hook set.**
    Historically both a `ruff format --check` gap and a `cargo fmt --check`
    gap let formatting drift accumulate silently for weeks because the
    GitLab lint job was narrower than the full pre-commit hook set — only
    GitHub's `Pre-Commit Check` (which runs the full hook set) caught
    either gap, and only on PRs that trigger it. Adding a new
    `.pre-commit-config.yaml` hook without checking whether `20-lint.yml`
    already covers it is a violation.
15. **GitHub's `Pre-Commit Check` runs against the squashed,
    exclusion-filtered public snapshot** (`scripts/publish_snapshot.sh`),
    not the full gitlab-tracked repo. A hook requirement that references a
    file excluded by `scripts/publish_exclusions.py` (e.g. `DECISIONS.md`,
    `docs/superpowers/plans/*`) will pass locally forever and fail
    permanently on the real GitHub run. A local `pre-commit run --all-files`
    green result does not prove GitHub's check will pass — only a real
    publish (or a scratch checkout with excluded paths removed) does.

## Test hygiene

16. **Long/slow test runs must be backgrounded and logged, never streamed
    into context.** Use `uv run poe run_bg <task>` (writes to
    `.pytest_logs/`) for the full suite or anything benchmark-shaped; a
    scoped run (a node-id, `-k`, or `-q` selection) is fine to run inline.
    An unscoped, whole-tree `pytest` run piped with `2>&1` into a
    foreground shell call is a violation.
17. **Never load a full `results.json` from `.spectrafit_reports/**` into
    context** — those files run tens of MB. Use the live API
    (`curl localhost:8000/api/report | jq '<field>'`), the
    `spectrafit-reports` MCP, or the cheap `run_audit` path instead.

## Design invariant

18. **Functionality before presentation (Invariant 0).** Before any
    web/CSS/design work lands for a metric, that metric must already be
    implemented at the source (Rust/Python), exposed as a real contract
    field, and verified against ground truth. Web work that renders a
    metric with no upstream Rust/Python/contract wire behind it (a mocked
    or hardcoded value presented as real) is a violation — see
    `.claude/skills/big-picture-driven-development/references/invariant-classes.md`.
