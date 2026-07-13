# Contributing to spectrafit-core

Thanks for your interest in contributing. This project is in **alpha** — APIs and
the benchmark contract may still change.

## Ground rules

- Be respectful; see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- By contributing you agree your contributions are licensed under the [MIT License](LICENSE).
- Report security issues privately — see [SECURITY.md](SECURITY.md), not the public tracker.

## Development setup

- Python ≥ 3.13, managed with [`uv`](https://docs.astral.sh/uv/); Rust toolchain (stable) + [`maturin`](https://www.maturin.rs/) for the PyO3 extension.
- Build the wheel locally: `uv run maturin develop`.
- Run the fast checks: `uv run poe lint_ci` (ruff CI-strict + ty), `uv run poe scenario_smoke`, `cargo test -p spectrafit-<crate>`.

## Conventions

This codebase is **Pydantic-first** and registry-driven. Before opening a PR, read:
- [`CLAUDE.md`](CLAUDE.md) — code conventions (Pydantic `BaseModel` over dataclass, `match`/`case` dispatch, registry over per-call maps) and the MCP-first tooling workflow.
- [`docs/methodology.md`](docs/methodology.md) — the cycle pattern and the four-step verification loop (tests → bench → gate → playwright).
- [`MODELS.md`](MODELS.md) — authoritative model formulas and parameter names.
- [`DECISIONS.md`](DECISIONS.md) — architecture decision records; add an entry for any load-bearing decision.
- Adding a model is a multi-crate change — follow the "Adding a New Benchmark Model" sequence in [`CLAUDE.md`](CLAUDE.md).

## Pull requests

- Branch from `main`; keep changes focused.
- Include tests (pytest / cargo / vitest as appropriate); the benchmark **gate** (`uv run spc-bench gate`) must stay green.
- The repository structure is enforced by `rrt folder check` (pre-commit + CI) — do not remove required root files or directories.
