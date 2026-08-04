---
icon: lucide/terminal
---

# Contributing to spectrafit-core

Thanks for your interest in contributing. This project is in **beta** — APIs and
the benchmark contract may still change.

## Ground rules

- Be respectful; see the [Code of Conduct](code-of-conduct.md).
- By contributing you agree your contributions are licensed under the MIT License.
- Report security issues privately — see [Security](../security.md), not the public tracker.

## Development setup

- Python ≥ 3.13, managed with [`uv`](https://docs.astral.sh/uv/); Rust toolchain (stable) + [`maturin`](https://www.maturin.rs/) for the PyO3 extension.
- Build the wheel locally: `uv run maturin develop`.
- Run the fast checks: `uv run poe lint_ci` (ruff CI-strict + ty), `uv run poe scenario_smoke`, `cargo test -p spectrafit-<crate>`.

## Third-party development tools

Beyond the language runtimes (Python, Rust, Node.js), the repository uses several
tools to enforce code quality, run tests, and manage hooks. Some are gates — a
commit or hook fails without them — while others improve the development loop
but degrade gracefully.

### Required

| Tool | Purpose | Install |
| :--- | :--- | :--- |
| `uv` | Python package manager & poe task runner; manages all Python dev dependencies (ruff, pytest, ty, maturin). | `curl -LsSf https://astral.sh/uv/install.sh \| sh` or `brew install uv` (macOS), `apt install pipx && pipx install uv` (Debian/Ubuntu) |
| `rustc` + `cargo` | Rust compiler and build tool; required for PyO3 extension and pre-commit hooks. | `rustup default stable` or `brew install rust` (macOS includes both). On Debian/Ubuntu: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` or `apt install cargo` (may be outdated; prefer rustup). |
| `node` + `npm` | JavaScript runtime and package manager; required for web dashboard tests (`uv run poe web_e2e`). | `brew install node` (macOS, includes npm) or `apt install nodejs npm` (Debian/Ubuntu). Requires Node ≥ 18. |
| `pre-commit` | Git hook manager; wires validation hooks into `.git/hooks/` (call `uv run pre-commit install` after cloning). | Included in `pyproject.toml` dev group — `uv sync` installs it. |

### Recommended

| Tool | Purpose | Install |
| :--- | :--- | :--- |
| `glab` | GitLab CLI; run `glab ci status -b <branch>` and `glab mr list` to check pipeline status locally. | `brew install glab` (macOS) or `apt install glab` (Debian/Ubuntu). See [glab install docs](https://github.com/profclems/glab#installation). Requires auth: `glab auth login`. |
| `gh` | GitHub CLI; useful for downloading GitHub Actions artifacts (`gh run download`) and logs (`gh run list --log`). | `brew install gh` (macOS) or `apt install gh` (Debian/Ubuntu). Requires auth: `gh auth login`. |
| `actionlint` | GitHub Actions workflow validator; lint `.github/workflows/` locally before pushing. | `go install github.com/rhysd/actionlint/cmd/actionlint@latest` or `brew install actionlint` (macOS). Works best with `shellcheck` on the PATH. |
| `shellcheck` | Shell script linter; validates bash/sh scripts in CI workflows (invoked by actionlint). | `brew install shellcheck` (macOS) or `apt install shellcheck` (Debian/Ubuntu). |
| `yamllint` | YAML linter; validates `.yml` and `.yaml` files (GitLab CI config, GitHub workflows). | `uv tool install yamllint` or `apt install yamllint` (Debian/Ubuntu). |
| `markdownlint` | Markdown linter; validates Markdown documentation for style consistency. | `npm install -g markdownlint-cli` or `apt install markdownlint` (Debian/Ubuntu). |

### Installing pre-commit hooks

After a fresh clone, activate the git hooks:

```bash
uv run pre-commit install
```

This wires 19 hooks into `.git/hooks/` and runs them automatically at pre-commit
and pre-push stages. Hooks validate Python/Rust/TypeScript formatting, linting,
type checking, and repo structure — they catch issues before CI. If a hook fails,
fix the issue and try the commit again (do not use `--no-verify` unless absolutely
necessary; it bypasses all gates).

## Git remotes

You may see up to four remotes configured (`gitlab`, `origin`, `github`,
`SpectraFit-Core`). Only `gitlab` (GitLab MPCDF) matters for **merging** work:
it's the primary remote and CI source of truth — every feature lands there as a
GitLab MR, no exceptions. `origin`, `github`, and `SpectraFit-Core` all point at
the same public GitHub mirror; `main` there is read-only from a merge
standpoint (see below), but pushing a **feature branch** there for fast CI
iteration is a sanctioned pattern — see "Fast iteration on GitHub" next.

The GitHub mirror's `main` is periodically republished as a single-commit
orphan snapshot: each publish force-pushes and discards all prior GitHub-`main`
history — but it never touches other GitHub branches. In practice: don't open a
PR *targeting* the GitHub mirror expecting it to merge there — any work merged
directly into GitHub `main`, including a Dependabot PR, is silently erased on
the next snapshot publish. Real merges always happen on GitLab.

## Fast iteration on GitHub

GitLab's full CI pipeline is the authoritative gate, but it's constrained by a
shared-runner queue and a hard 1-hour job timeout — a lone feature-branch push
there can take a while, especially across several iterative pushes. GitHub
Actions isn't subject to that constraint and its lint/test/coverage rigor is
equal-or-better for most jobs, so it's a legitimate fast-feedback lane for
iteration:

1. Push your feature branch to `github`: `git push github my-feature`. Safe —
   the mirror's auto-publish force-push only ever overwrites GitHub `main`,
   never other branches.
2. Open a **draft PR** on GitHub against `main` — this is what actually
   triggers the GitHub Actions checks; a bare branch push alone does not.
   Iterate freely; each push re-runs the same checks.
3. **Know the gap**: GitHub Actions does *not* run the NIST StRD verification
   suite or the Playwright render-walk over the benchmark report — both are
   GitLab-exclusive and still block merge.
4. When ready, land it on GitLab — the backport tooling lists the pending
   commits with a cherry-pick or squash-merge recipe.
5. Open the real GitLab MR from that recipe. Its pipeline runs the full
   battery, including both GitLab-exclusive gates, before merge.
6. Merge the GitLab MR; close (don't merge) the GitHub draft PR — the next
   auto-publish overwrites GitHub `main` regardless.

GitLab remains the source of truth throughout; this lane only makes the
iteration loop faster. See the [GitHub mirror workflow](github-mirror-workflow.md)
page for the full mechanism.

## Conventions

This codebase is **Pydantic-first** and registry-driven. Before opening a PR,
read:

- `CLAUDE.md` (repo root) — code conventions (Pydantic `BaseModel` over
  dataclass, `match`/`case` dispatch, registry over per-call maps) and the
  MCP-first tooling workflow.
- The [model reference](../reference/models/index.md) — authoritative model
  formulas and parameter names.
- `DECISIONS.md` (repo root, internal-only) — architecture decision records;
  add an entry for any load-bearing decision.
- Adding a model is a multi-crate change — see [Adding a model](../how-to/adding-a-model.md).

## Pull requests

- Branch from `main`; keep changes focused.
- Include tests (pytest / cargo / vitest as appropriate); the benchmark
  **gate** (`uv run poe benchmark_gate`, or `uv run python -m oracles.cli
  gate`) must stay green.
- The repository structure is enforced by `rrt folder check` (pre-commit +
  CI) — do not remove required root files or directories.
