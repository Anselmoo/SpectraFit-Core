---
icon: lucide/terminal
description: Ground rules and development setup for contributing to spectrafit-core — required toolchain, build commands, and the required vs. optional third-party dev tools.
tags:
  - Rust
  - Python
---

# Contributing to spectrafit-core

Thanks for your interest in contributing. This project is in **beta** — APIs and
the benchmark contract may still change.

## Ground rules

- Be respectful; see the [Code of Conduct](code-of-conduct.md).
- By contributing you agree your contributions are licensed under the MIT License.
- Report security issues privately — see [Security](../security.md), not the public tracker.

## Development setup

- Python $\geq$ 3.13, managed with [`uv`](https://docs.astral.sh/uv/); Rust toolchain (stable) + [`maturin`](https://www.maturin.rs/) for the PyO3 extension.
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
| `node` + `npm` | JavaScript runtime and package manager; required for web dashboard tests (`uv run poe web_e2e`). | `brew install node` (macOS, includes npm) or `apt install nodejs npm` (Debian/Ubuntu). Requires Node `^20.19.0 || >=22.12.0` (the Vite 7 toolchain's `engines` constraint in `web/package-lock.json`); CI runs Node 22. |
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

This wires **29 hooks** into `.git/hooks/`, across **three** stages —
`pre-commit`, `commit-msg`, and `pre-push` (`default_install_hook_types` in
`.pre-commit-config.yaml`). 27 of the 29 run automatically at one or more of
those stages; the other two (`rrt-doctor`, `rrt-release-check`) are
`manual`-stage only and have to be invoked explicitly (for example
`pre-commit run rrt-doctor --hook-stage manual`) — they never fire on a normal
commit or push. Hooks validate Python/Rust/TypeScript formatting, linting,
type checking, and repo structure — they catch issues before CI. If a hook
fails, fix the issue and try the commit again.

A few of these are easy to miss because nothing above mentions them by name:

- **`commit-msg` is a real stage, not a formality** — it's what actually
  rejects your first commit if the subject line doesn't parse.
  `rrt-commit-subject` enforces Conventional Commits there: the subject must
  match `<type>[(scope)]: <description>`, with `type` one of `feat`, `fix`,
  `chore`, `docs`, `refactor`, `test`, `ci`, `perf`, `style`, `build`, or
  `deps` — e.g. `fix(cli): handle empty stdin`. `Merge …` subjects, and
  `fixup!`/`squash!` prefixes wrapping an otherwise-conventional subject, are
  exempt.
- **`rrt-branch-name`** (`pre-commit` stage) enforces the same convention on
  your branch name: `<type>/[<scope>-]<kebab-case-description>` using the
  same `type` list, or one of `main`/`master`/`develop`,
  `release/v<semver>`, or a `claude/…`/`codex/…`/`copilot/…`/
  `dependabot/…`/`renovate/…` prefix.
- **`rrt-changelog`** (`pre-commit` stage) requires a `CHANGELOG.md` entry
  when the commit type maps to a real changelog section — `feat`, `fix`,
  `refactor`, `perf`, `docs`, `style`, or anything marked as a breaking
  change. `chore`, `ci`, `build`, `test`, and `deps` commits are exempt (they
  map to "Maintenance", which isn't gated).
- **Two hooks rewrite files as part of the commit**, not just check them:
  `pre-merge-arch-tree` regenerates `architecture.md`'s embedded directory
  tree, and `self-heal-automation` applies deterministic safe-fixes to hook
  and skill/agent metadata — both re-stage what they change, so the tree you
  end up committing can differ slightly from what you `git add`ed.
- **`cargo-clippy` and `cargo-check` run workspace-wide** on *any* `.rs` file
  change, not just the file(s) you touched (`pass_filenames: false`) — a
  one-line Rust edit can trigger a full-workspace clippy/check pass.

!!! warning
    Do not use `--no-verify` unless absolutely necessary; it bypasses all gates.

## Git remotes

You may see up to four remotes configured (`gitlab`, `origin`, `github`,
`SpectraFit-Core`). Only `gitlab` (GitLab MPCDF) matters for **merging** work:
it's the primary remote and CI source of truth — every feature lands there as a
GitLab MR, no exceptions. `origin`, `github`, and `SpectraFit-Core` all point at
the same public GitHub mirror, and nobody pushes to them by hand — see
"Pushing only to GitLab" below.

The GitHub mirror's `main` used to be republished as a single-commit orphan
snapshot on every publish, force-pushing over and discarding all prior
GitHub-`main` history. It's now synced **append-only and anonymously**: each
publish builds one bot-authored commit whose tree is GitLab `main` reduced to
the publish scope (see `scripts/publish_exclusions.py`), parented on the
*current* GitHub `main` — not an orphan root — pushes it to `sync/gitlab`,
opens (or updates) a PR `sync/gitlab -> main` so the mirror's CI runs, and
fast-forwards `main` to it once the required checks pass. GitHub `main`'s history
now grows forward, one sync commit per GitLab publish, instead of being
discarded each time — and, as before, other GitHub branches are never
touched. In practice: don't open a PR *targeting* the GitHub mirror expecting
a direct merge there to be the final word — any work merged straight into
GitHub `main`, including a Dependabot PR, is picked up and carried over to
GitLab automatically by the scheduled backport job (see the
[GitHub mirror workflow](github-mirror-workflow.md) page), not silently
erased. Real merges you make yourself still always happen
on GitLab.

## Pushing only to GitLab

Push feature branches to `gitlab` only. Its MR pipeline is the gate, including
the NIST StRD verification suite and the Playwright render-walk over the
benchmark report, neither of which runs on GitHub.

The GitHub mirror is written only by CI (`publish:github` ->
`scripts/publish_sync.py`), which publishes GitLab's tree reduced to the
include list in `scripts/publish_exclusions.py`. A hand-pushed branch would
carry the full, unfiltered tree, so it is refused by the `guard-public-push`
pre-push hook and by the mirror's server-side push rules (see
[Who may write to the mirror](github-mirror-workflow.md#who-may-write-to-the-mirror)).
Disabling the push URL of each GitHub remote closes the `--no-verify` gap too:

```bash
git remote set-url --push github DISABLED   # repeat for origin / SpectraFit-Core
```

## Conventions

This codebase is **Pydantic-first** and registry-driven. Before opening a PR,
read:

- `CLAUDE.md` (repo root) — code conventions (Pydantic `BaseModel` over
  dataclass, `match`/`case` dispatch, registry over per-call maps) and the
  Model Context Protocol (MCP)-first tooling workflow.
- The [Model Reference](../reference/models/index.md) — authoritative model
  formulas and parameter names.
- Adding a model is a multi-crate change — see [Adding a model](../how-to/adding-a-model.md).

## Pull requests

- Branch from `main`; keep changes focused.
- Include tests (pytest / cargo / vitest as appropriate); the benchmark
  **gate** (`uv run poe benchmark_gate`, or `uv run python -m oracles.cli
  gate`) must stay green.
- The repository structure is enforced by `rrt folder check` (pre-commit +
  CI) — do not remove required root files or directories.

## Next steps

- **Understand the tooling you just installed** — [`pyproject.toml`,
  explained](project-configuration.md) covers why the `poe` tasks, coverage
  floors, and lint rules behind the checks above are configured the way they
  are.
- **See the codebase you just set up** — [Architecture](architecture.md)
  covers the directory layout, the model composition DAG, and where Python
  meets Rust at the PyO3 boundary.
