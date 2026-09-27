# Contributing to spectrafit-core

Thanks for your interest in contributing. This project is in **beta** — APIs and
the benchmark contract may still change.

## Ground rules

- Be respectful; see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- By contributing you agree your contributions are licensed under the [MIT License](LICENSE).
- Report security issues privately — see [SECURITY.md](SECURITY.md), not the public tracker.

## Development setup

- Python ≥ 3.13, managed with [`uv`](https://docs.astral.sh/uv/); Rust toolchain (stable) + [`maturin`](https://www.maturin.rs/) for the PyO3 extension.
- Build the wheel locally: `uv run maturin develop`.
- Run the fast checks: `uv run poe lint_ci` (ruff CI-strict + ty), `uv run poe scenario_smoke`, `cargo test -p spectrafit-<crate>`.

## Where development happens

Development and the authoritative CI run on an institutional GitLab instance;
this GitHub repository is its public mirror. Every change reaches the mirror the same way: after a green
pipeline on GitLab `main`, a sync job opens a pull request here that carries
GitLab's tree (reduced to the public publish scope) and is squash-merged.
Contributions made on GitHub flow back to GitLab automatically — see
"External contributions" below and
[`docs/contributor-guide/github-mirror-workflow.md`](docs/contributor-guide/github-mirror-workflow.md)
for the mechanism, including why the two directions cannot loop.

## Pushing: GitLab only

Push your branches to the GitLab remote and nowhere else. The GitLab MR pipeline is the gate, including the two GitLab-exclusive checks (`audit:trust`, the NIST StRD verification suite, and `report_e2e`, the Playwright render-walk of the benchmark report).

The GitHub mirror is written **only** by CI: `publish:github` runs `scripts/publish_sync.py`, which publishes GitLab's tree reduced to the include list in `scripts/publish_exclusions.py`. A branch pushed to GitHub by hand would carry the full, unfiltered tree — every private working directory included — so it is refused twice over: locally by the `guard-public-push` pre-push hook (`scripts/guard_public_push.py`) and server-side by the mirror repository's push rules (see [`docs/contributor-guide/github-mirror-workflow.md`](docs/contributor-guide/github-mirror-workflow.md#who-may-write-to-the-mirror)). To make a stray push impossible even with `--no-verify`, disable the push URL of every GitHub remote in your clone: `git remote set-url --push <github-remote> DISABLED`.

**Branches on the mirror.** Besides `main` and the sync's own `sync/gitlab`, branches exist there only for GitHub-native work such as Dependabot updates. `uv run poe check_stale_github_branches` lists every such branch with un-backported commits older than 14 days (`--min-age-days` to tune, `--strict` to exit non-zero); `uv run poe backport_github <branch>` prints the recipe to carry one over to GitLab.

## External contributions (no GitLab access)

An outside contributor — someone without an account on the institutional
GitLab instance — opens a **normal GitHub pull request** against `Anselmoo/SpectraFit-Core`'s `main` branch, same
as on any GitHub project. Once it's reviewed and merged (squash) on GitHub, it
becomes a commit on `github/main` past the last GitLab sync's boundary — the
scheduled `backport:github` job (`.gitlab/75-backport.yml`, see
[`docs/contributor-guide/github-mirror-workflow.md`](docs/contributor-guide/github-mirror-workflow.md#mechanism-2-the-scheduled-auto-backport-github-gitlab))
finds it automatically, cherry-picks it onto a `backport/github-<date>`
branch, and opens the GitLab MR that actually lands it on the source of
truth. No separate intake channel or manual maintainer replay is needed —
treat opening a GitHub PR (or issue, for a proposal without code) as the
real, supported path in.

Please keep such PRs to files that exist on this mirror. The sync publishes
only the public scope, so a new file outside it would be carried over to GitLab
and then disappear from GitHub on the next sync — open an issue first if you
think something outside the current tree is needed.

## Conventions

This codebase is **Pydantic-first** and registry-driven. Before opening a PR, read:
- [`CLAUDE.md`](CLAUDE.md) — code conventions (Pydantic `BaseModel` over dataclass, `match`/`case` dispatch, registry over per-call maps) and the MCP-first tooling workflow.
- [Model Reference](docs/reference/models/index.md) — authoritative model formulas and parameter names.
- Explain any load-bearing design decision in the PR description, so the rationale is reviewable alongside the change.
- Adding a model is a multi-crate change — follow the "Adding a New Benchmark Model" sequence in [`CLAUDE.md`](CLAUDE.md).

## Pull requests

- Branch from `main`; keep changes focused.
- Include tests (pytest / cargo / vitest as appropriate); the benchmark **gate** (`uv run poe benchmark_gate`, or `uv run python -m oracles.cli gate`) must stay green.
- The repository structure is enforced by `rrt folder check` (pre-commit + CI) — do not remove required root files or directories.

## Review process

The project currently has a single maintainer, who reviews every contribution.
[`CODEOWNERS`](CODEOWNERS) records the owner per area. A change is accepted
when the automated gates pass (CI, the benchmark gate, and the structure
checks above) and the maintainer agrees with the design; there is no fixed
response-time commitment during the beta.
