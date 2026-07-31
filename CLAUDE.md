# Developer Guidelines & MCP Protocol (SpectraFit-Core)

CRITICAL: Internal memory is your LAST resort. You MUST use the Model Context Protocol (MCP) tools and project CLI commands as your default action path. This is a **polyglot** repo — Rust (`crates/`), Python (`python/`), TypeScript/React (`web/`), and a Zensical docs site (`docs/`) — pick the tool/command for the stack you're actually touching, not just the Python defaults.

## 1. MCP & Tool Execution Matrix (WHICH-TOOL-WHEN)

Before executing any terminal command (`grep`, `find`, `cat`) or relying on training data, you MUST invoke the appropriate MCP server or CLI tool from this matrix:

| Objective / Task | REQUIRED Tool / Command | Protocol & Constraints |
| :--- | :--- | :--- |
| **Locate code, symbols, references** | MCP: `serena` (`find_symbol`, `find_referencing_symbols`) | **Mandatory** over raw `grep` for symbol-level lookups — works across Rust, Python, and TypeScript alike. |
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
| **Durable Fact Storage** | File-based Memory (`~/.claude/projects/...`) | **DO NOT use `serena.write_memory`** (it does not auto-surface!). Write to `MEMORY.md` index or `DECISIONS.md`. |

### Tool Composition Chain (Examples)
- Single-stack fix: `serena` (locate symbol) ➔ `context7` (confirm API) ➔ `github` (read upstream PR) ➔ Record in file-based memory/`DECISIONS.md`.
- Cross-stack fix: `zen-of-languages` (spot the cross-language drift) ➔ `serena` (locate the exact symbol per language) ➔ fix each side ➔ `analyzer` (Python) / `cargo clippy` (Rust) / `npm run typecheck` (web) to verify per-language ➔ Record in `DECISIONS.md`.

---

## 2. Hard Constraints & Escalation Paths

- **The 1-Retry Rule:** If an MCP connection fails, a tool returns 401/403, or a CLI is missing, **STOP immediately and ask the user**. Never silently fall back to a degraded or manual path.
- **Durable Memory Boundary:** `serena.write_memory` is navigation-only. Real, session-surfaced facts must be written directly to the file-based project memory (`MEMORY.md` / `DECISIONS.md`).

---

## 3. Polyglot Stack Map (WHERE-LIVES-WHAT)

| Directory | Language / Stack | Toolchain | Primary Commands |
| :--- | :--- | :--- | :--- |
| `crates/*` (11 crates) | Rust (PyO3 extension) | `cargo`, `maturin` | `cargo check --workspace`, `cargo clippy --workspace --all-targets --all-features`, `uv run --with maturin maturin develop --release` |
| `python/oracles/`, `python/spectrafit_core/` | Python (Pydantic-first) | `uv`, `ruff`, `ty`, `pytest` | `uv run poe lint_ci`, `uv run poe coverage`, `uv run poe scenario_smoke`, `uv run poe benchmark_gate` |
| `web/` | TypeScript / React (Vite) | `npm`, `vitest`, Playwright | `cd web && npm run typecheck && npm run test`, `uv run poe web_smoke`, `uv run poe web_e2e` |
| `docs/`, `zensical.toml` | Zensical docs site | `uv run --group docs zensical` | `uv run poe docs_build`, `uv run poe docs_serve` |

---

## 4. Code Conventions (Per-Stack)

### Python (Pydantic-First)
- **Data Modeling:** Use Pydantic `BaseModel` exclusively (No `@dataclass`). Use `ConfigDict(arbitrary_types_allowed=True)` for numpy arrays; use `extra="forbid"` for contracts.
- **Declarative Registries:** Registry-over-map. Register new shapes once in `oracles.models.MODEL_REGISTRY`. Backends must read the registry, never a private map.
- **Strict Dispatching:** Use `match`/`case` over `if/elif ==` chains for dispatching on discriminators. *Enforced:* 2+ `if/elif` branches on the same variable in `python/oracles/**` or `tests/**` will fail at edit time (Exit 2).

### Rust (`crates/*`)
- **PyO3 boundary:** every `#[pyfunction]` must return JSON strings only — enforced by the `pre-merge-pyO3` pre-commit hook.
- **Crate DAG:** dependency direction is enforced by the `pre-merge-dag` hook — add or move code to satisfy it, don't introduce a back-edge as a shortcut.
- **Schema sync:** Python↔Rust JSON-boundary alignment is checked by `pre-merge-schema-sync` — if you change `ModelTypeStr` or a serde-tagged struct, update the matching Python side in the same commit.
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
