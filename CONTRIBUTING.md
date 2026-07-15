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

## Git remotes

You may see up to four remotes configured (`gitlab`, `origin`, `github`, `SpectraFit-Core`). Only `gitlab` (GitLab MPCDF) matters for **merging** work: it's the primary remote and CI source of truth (see [`CLAUDE.md`](CLAUDE.md)'s remote-primary policy) — every feature lands there as a GitLab MR, no exceptions. `origin`, `github`, and `SpectraFit-Core` all point at the same public GitHub mirror; `main` there is read-only from a merge standpoint (see below), but pushing a **feature branch** there for fast CI iteration is a sanctioned pattern — see "Fast iteration on GitHub" next.

The GitHub mirror's `main` is periodically republished as a single-commit orphan snapshot via `rrt git publish-snapshot` (see `.gitlab/70-publish.yml` / `scripts/publish_snapshot.sh` for the mechanics; as of 2026-07-14 this fires automatically after every successful GitLab pipeline on `main`, not just on a manual click). Each publish force-pushes and discards all prior GitHub-`main` history — but it never touches other GitHub branches. In practice: don't open a PR *targeting* the GitHub mirror expecting it to merge there — any work merged directly into GitHub `main`, including a Dependabot PR, is silently erased on the next snapshot publish. Real merges always happen on GitLab.

## Fast iteration on GitHub

GitLab's full CI pipeline is the authoritative gate, but it's constrained by GWDG's shared-runner queue and a hard 1-hour job timeout — a lone feature-branch push there can take a while, especially across several iterative pushes. GitHub Actions isn't subject to that constraint and its lint/test/coverage rigor is equal-or-better for most jobs, so it's a legitimate fast-feedback lane for iteration:

1. Push your feature branch to `github`: `git push github my-feature`. Safe — the mirror's auto-publish force-push only ever overwrites GitHub `main`, never other branches.
2. Open a **draft PR** on GitHub against `main` — this is what actually triggers `.github/workflows/ci.yml` and `pre-commit-check.yml`; a bare branch push alone does not. Iterate freely; each push re-runs the same checks.
3. **Know the gap**: GitHub Actions does *not* run `audit:trust` (the NIST StRD / W1-W8 verification-wire suite) or the Playwright `report_e2e` render-walk inside `build:report_html` — both are GitLab-exclusive and still block merge.
4. When ready, land it on GitLab: `uv run poe backport_github my-feature` (add `--squash` for a WIP-heavy branch) lists the pending commits with a cherry-pick or squash-merge recipe.
5. Open the real GitLab MR from that recipe. Its pipeline runs the full battery, including both GitLab-exclusive gates, before merge.
6. Merge the GitLab MR; close (don't merge) the GitHub draft PR — the next auto-publish overwrites GitHub `main` regardless.

GitLab remains the source of truth throughout; this lane only makes the iteration loop faster. See `docs/superpowers/specs/2026-07-12-github-mirror-backport-recipe.md` for the full mechanism.

## Conventions

This codebase is **Pydantic-first** and registry-driven. Before opening a PR, read:
- [`CLAUDE.md`](CLAUDE.md) — code conventions (Pydantic `BaseModel` over dataclass, `match`/`case` dispatch, registry over per-call maps) and the MCP-first tooling workflow.
- [`docs/methodology.md`](docs/methodology.md) — the cycle pattern and the four-step verification loop (tests → bench → gate → playwright).
- [`MODELS.md`](MODELS.md) — authoritative model formulas and parameter names.
- [`DECISIONS.md`](DECISIONS.md) — architecture decision records; add an entry for any load-bearing decision.
- Adding a model is a multi-crate change — follow the "Adding a New Benchmark Model" sequence in [`CLAUDE.md`](CLAUDE.md).

## Pull requests

- Branch from `main`; keep changes focused.
- Include tests (pytest / cargo / vitest as appropriate); the benchmark **gate** (`uv run poe benchmark_gate`, or `uv run python -m oracles.cli gate` — the `spc-bench` console script was removed 2026-06-20) must stay green.
- The repository structure is enforced by `rrt folder check` (pre-commit + CI) — do not remove required root files or directories.
