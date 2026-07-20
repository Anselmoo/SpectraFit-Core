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
