# Developer Guidelines & MCP Protocol (SpectraFit-Core)

CRITICAL: Internal memory is your LAST resort. You MUST use the Model Context Protocol (MCP) tools and project CLI commands as your default action path. This is a **polyglot** repo — Rust (`crates/`), Python (`python/`), TypeScript/React (`web/`), and a Zensical docs site (`docs/`) — pick the tool/command for the stack you're actually touching, not just the Python defaults.

## 1. MCP & Tool Execution Matrix (WHICH-TOOL-WHEN)

Before executing any terminal command (`grep`, `find`, `cat`) or relying on training data, you MUST invoke the appropriate MCP server or CLI tool from this matrix:

| Objective / Task | REQUIRED Tool / Command | Protocol & Constraints |
| :--- | :--- | :--- |
| **Check Python Types & Lints** | MCP: `analyzer` (`mcp__analyzer__ruff-check-ci`, `mcp__analyzer__ty-check`) | **Python-only** (`python/**`, `tests/**`) — **MUST run before any `git push`** touching those paths. *Caveat:* `ty-check` isolates snippets; verify with `uv run ty check` if relative imports fail. `analyzer` does **not** cover Rust or TypeScript — see the next two rows. |
| **Check Rust fmt/lint/compile** | CLI (no MCP wraps cargo): `cargo fmt --check`, `cargo clippy --workspace --all-targets --all-features`, `cargo check --workspace` | Enforced as pre-commit/pre-push hooks (`cargo-fmt`, `cargo-clippy`, `cargo-check`) — run them yourself before relying on the hook to catch it at commit time. |
| **Cross-language architecture/idiom audit** | MCP: `zen-of-languages` | Use for idiom/architecture checks spanning `crates/` (Rust) + `python/` + `web/` (TypeScript) at once — the one tool that reasons across the whole polyglot surface instead of one language at a time. |
| **Query benchmark run artifacts** | MCP: `spectrafit-reports` (`list_runs`, `latest_results`, `load_manifest`, `find_report_html`) | Use instead of hand-globbing `.spectrafit_reports/**` for run results/manifests. |
| **Web / report E2E & UI testing** | MCP: `playwright` (`mcp__playwright__browser_*`) | Use for interactive `web/` or bundled `report.html` verification. `uv run poe web_e2e` / `poe report_e2e` run the equivalent specs headless via CLI when a live browser isn't needed. |
| **Release & Version State** | MCP: `rrt` (`mcp__rrt__rrt_health`, `rrt_doctor`, `rrt_drift`) | Use **before** hand-grepping `pyproject.toml` or `Cargo.toml`. *Safety:* Mutating tools default to `dry_run=True`; ask before confirming. |
| **Library / External API Docs** | MCP: `context7` | Query library docs (faer, pyo3, lmfit, scipy, pydantic, React/Vite) **before** writing code. |
| **Upstream Repos, Issues, PRs** | MCP: `github` | Use for searching code/issues/PRs. Prefer over `gh` CLI (unreliable OAuth). |
| **GitLab Pipeline / MR Status** | CLI: `glab` (Authenticated to `gitlab.mpcdf.mpg.de`) | Run `glab ci status -b <branch>` or `glab mr list`. **Never** use `WebFetch` (auth-less 403). |
| **General Web / GHA Logs** | WebSearch / WebFetch / `gh run view --log` | Use ONLY for topics outside repo scope. Note: log downloads require `gh` CLI. |
| **Durable Fact Storage** | File-based Memory (`~/.claude/projects/...`) | Write to `MEMORY.md` index or `DECISIONS.md`. |

### Tool Composition Chain (Examples)
- Single-stack fix: `Grep` (locate symbol) ➔ `context7` (confirm API) ➔ `github` (read upstream PR) ➔ Record in file-based memory/`DECISIONS.md`.
- Cross-stack fix: `zen-of-languages` (spot the cross-language drift) ➔ `Grep` (locate the exact symbol per language) ➔ fix each side ➔ `analyzer` (Python) / `cargo clippy` (Rust) / `npm run typecheck` (web) to verify per-language ➔ Record in `DECISIONS.md`.

---

## 2. Hard Constraints & Escalation Paths

- **The 1-Retry Rule:** If an MCP connection fails, a tool returns 401/403, or a CLI is missing, **STOP immediately and ask the user**. Never silently fall back to a degraded or manual path.
- **`DECISIONS.md` is append-only starting 2026-08-08.** All prior ADRs live in `DECISIONS-archive.md` (same root, renamed via `git mv` to preserve history) — consult it for historical decisions, but append new entries only to `DECISIONS.md`.
- **`analysis/` layout + a write-gate gotcha:** see `analysis/INDEX.md` before writing anywhere under `analysis/`. Short version: once `analysis/self-assess/` exists (it does, permanently), the `self-assess` plugin's `guard_target_edit.py` `PreToolUse` hook denies every `Write`/`Edit`/`MultiEdit` call repo-wide unless `.claude/self-assess.local.md` sets `idiom_fix.mode: 'fix'` or `transform.mode: 'execute'` — **do not set those** (that authorizes self-assess's own automated skills to edit source, not "let me keep working"). Use `Bash` (heredoc / `sed` / a small Python script) instead; the hook only matches those three tool names.

---

## 3. Polyglot Stack Map (WHERE-LIVES-WHAT)

| Directory | Language / Stack | Toolchain | Primary Commands |
| :--- | :--- | :--- | :--- |
| `crates/*` (11 crates) | Rust (PyO3 extension) | `cargo`, `maturin` | `cargo check --workspace`, `cargo clippy --workspace --all-targets --all-features`, `uv run --with maturin maturin develop --release` |
| `python/oracles/`, `python/spectrafit_core/` | Python (Pydantic-first) | `uv`, `ruff`, `ty`, `pytest` | `uv run poe lint_ci`, `uv run poe coverage`, `uv run poe scenario_smoke`, `uv run poe benchmark_gate` |
| `web/` | TypeScript / React (Vite) | `npm`, `vitest`, Playwright | `cd web && npm run typecheck && npm run test`, `uv run poe web_smoke`, `uv run poe web_e2e` |
| `docs/`, `zensical.toml` | Zensical docs site | `uv run --group docs zensical` | `uv run poe docs_build`, `uv run poe docs_serve` |
| `.superpowers/` | Superpowers working artifacts (specs, plans, ledgers) | — | see below |
| `analysis/` | codebase-consistency / self-assess / andon output | — | written by the plugins' own skills |

### Where working artifacts go — `.superpowers/`, never `docs/`

**`.superpowers/` (dot-prefixed, top level) is THE standard.** Brainstorming specs,
writing-plans plans and semantic-debugging ledgers go in `.superpowers/{specs,plans,ledgers}/`.

- **Never `docs/`.** `docs/` is the published Zensical site source — product
  documentation only. The superpowers skills default to `docs/superpowers/**`;
  override it every time.
- **Never the undotted `superpowers/`.** `superpowers/*` appears in
  `scripts/publish_exclusions.py` purely as a safety net so the wrong form cannot
  silently publish. It is not a second valid location — do not create it.
- **One archived third location exists.** `.claude/docs/superpowers/plans/` holds four
  pre-2026-08-02 docs plans. It is publish-excluded via `.claude/docs/*`, so it does not
  leak — but it is neither `.superpowers/` nor the forbidden undotted form, so it is named
  here rather than left to make the rule above look approximate. Do not add to it.
- **`analysis/` is NOT dot-prefixed, deliberately.** The codebase-consistency
  plugin writes `analysis/<area>/…` as a hardcoded path; renaming it breaks every
  `/consistency-*` run. Rule of thumb: **dot-prefix what we control, leave
  tool-owned paths as the tool names them.**

A new top-level directory is **published to the public GitHub mirror by default** —
`EXCLUDE_PATTERNS` is an allowlist of paths to *strip*, so anything absent from it
ships. Adding a working-artifact directory means adding it there **and** to
`pyproject.toml`'s `[tool.rrt.publish_targets.github].exclude` mirror, then
re-running `tests/meta/test_publish_exclusions.py`, which pins the set exactly.

---

## 4. Code Conventions (Per-Stack)

### Python (Pydantic-First)
- **Data Modeling:** Use Pydantic `BaseModel` exclusively (No `@dataclass`). Use `ConfigDict(arbitrary_types_allowed=True)` for numpy arrays; use `extra="forbid"` for contracts.
- **Declarative Registries:** Registry-over-map. Register new shapes once in `oracles.models.MODEL_REGISTRY`. Backends must read the registry, never a private map.
- **Strict Dispatching:** Use `match`/`case` over `if/elif ==` chains for dispatching on discriminators. *Enforced:* 2+ `if/elif` branches on the same variable in `python/oracles/**` or `tests/**` will fail at edit time (Exit 2).
- **Math notation in Python docstrings is real LaTeX, never a hand-typed unicode/ASCII approximation** — write `$\chi^2$`, `$\pm$`, `$\kappa(J)$`, not `χ²`, `±`, `κ(J)`. This rule is **Python-only** for now; Rust/TS doc comments aren't covered. A class docstring or `Field(description=...)` on any Pydantic model serialized into `BenchReport` (`python/oracles/bench_contract.py`, `trust_ledger.py`, `contract.py`) becomes OpenAPI `description` text byte-for-byte — editing it, even for "docs-only" cleanup, **is a contract change**. If you touch one of those descriptions, run `uv run poe contract_regen` before committing (regenerates the Python golden, `web/src/openapi.gen.ts`, and `web/openapi.snapshot.json` together) — do **not** "fix" a resulting golden-drift failure by de-LaTeX-ing the source. **Enforced** by `scripts/audit_latex.py` (blocking since 2026-08-21, run by `uv run poe audit_latex` in both CI pipelines): an AST pass flags unicode math in every docstring and `Field(description=...)` under `python/**`, and it also resolves `--8<--` snippet includes so files outside `docs/` that render on a docs page (e.g. root `LIMITATIONS.md`) are covered too. *Boundary:* Greek letters, super/subscript digits and analysis operators (`± ≤ ≥ ≠ ≈ ∞ √ ∑ ∫ ∂ ∇ ‖ ·`) must be LaTeX; prose `→` and `×` are deliberately **out** of scope — see `UNICODE_MATH_GLYPHS` in that script to revisit the line. Separately, `pre-merge-contract-golden` guards the OpenAPI golden itself (schema drift only, not notation).
- **Import style differs by package, deliberately:** `spectrafit_core` uses sibling-relative imports (`from .models import …`), while `oracles` uses absolute imports (`from oracles.models import …`); both pass ruff TID. Do not unify.

### Rust (`crates/*`)
- **PyO3 boundary:** every `#[pyfunction]` must return a JSON string only — **with exactly one exemption**, `fit_arrays_numpy`, which returns `(json, ndarray)` so the fitted curve on the zero-copy path never round-trips through JSON. Enforced by the `pre-merge-pyO3` hook (wired at `pre-commit` **and** `pre-push` in `.pre-commit-config.yaml`), which joins each multi-line signature before testing its return type and carries that single name in a commented allowlist. Adding a second exemption means editing the hook's allowlist *and* this bullet — don't do one without the other.
- **PyO3 panic boundary:** every solver-invoking `#[pyfunction]` wraps its body in the `guard` helper (`catch_unwind` → `PyValueError`), so a Rust panic reaches Python as a catchable `ValueError` instead of an uncatchable `pyo3_runtime.PanicException`. The array paths capture PyO3 handles and so pass `std::panic::AssertUnwindSafe`; `tests/unit/spectrafit_core/test_panic_boundary.py` pins the roster statically.
- **Crate DAG:** dependency direction is enforced by the `pre-merge-dag` hook — add or move code to satisfy it, don't introduce a back-edge as a shortcut.
- **Schema sync:** Python↔Rust JSON-boundary alignment is checked by `pre-merge-schema-sync`, which compares serde **wire field names** in `crates/spectrafit-types/src/types.rs` against their Pydantic mirrors in `python/spectrafit_core/` (9 registered pairings, static stdlib parse, ~0.6 s). Renaming a field — or its `#[serde(rename)]` — on one side only fails the gate, and adding a new serde struct fails until you register it in the hook's `PAIRS`. The `ModelTypeStr` variant set is **not** covered here: that is `enforce-modeltype-parity.sh` plus `tests/parity/test_schema_parity.py`.
- **Binding audit:** every new `#[pyfunction]` registered in `crates/spectrafit-core/src/lib.rs` or `Solver::` variant in `crates/spectrafit-solver/src/dispatch.rs` needs a one-line entry in `scripts/binding_audit_notes.toml`, then run `uv run poe audit_bindings_regen` — enforced by `scripts/audit_bindings.py` in CI (checked directly against that TOML file, no `docs/` dependency).

### TypeScript / React (`web/`)
- Contract types are generated, not hand-written: after any FastAPI schema change, run `uv run poe contract_regen` (repo root) or `npm run contract` (inside `web/`), then `npm run check:contract` to verify no drift.
- Run `npm run typecheck` before committing — `npm run build` runs `tsc --noEmit` first anyway, so a typecheck failure blocks the build.

### Multi-Crate Model Sequence (cross-stack)
- Adding a model requires the full chain: Rust kernel ➔ `ModelTypeStr` ➔ `spectrafit-builder` gate ➔ Python `ModelType` ➔ bench registry ➔ case recipe. No shortcuts.

---

## 5. Development Cycle Methodology

- **Rust loop:** `cargo check --workspace` ➔ `cargo clippy --workspace --all-targets --all-features` ➔ `uv run --with maturin maturin develop --release` (rebuild the extension — Python-side tests won't see Rust changes until this runs) ➔ if you added/removed a `#[pyfunction]` or `Solver::` variant, `uv run poe audit_bindings_regen`.
- **Python loop:** `uv run poe lint_ci` ➔ `uv run poe coverage` ➔ `uv run poe benchmark_gate` (spectrafit-vs-lmfit regression gate).
- **Web loop:** `uv run poe web_smoke` (typecheck + vitest + build) ➔ `uv run poe web_e2e` (Playwright; requires `npx playwright install chromium` once).
- **Pre-Push Smoke Check:** Run `uv run poe scenario_smoke` for a fast (<500 ms) cross-check before pushing any model changes — this is the minimum bar, not a substitute for the full per-stack loop above when a change spans more than one stack.
