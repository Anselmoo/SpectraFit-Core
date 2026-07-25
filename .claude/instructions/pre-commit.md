> Applies to: **/*.{py,rs}

# Pre-commit hooks & formatting

Keep repository formatting and static analysis deterministic and automated. Install and run pre-commit locally, and run the same checks in CI on every PR.

## Rules

- Use `pre-commit` for developer-local checks. Required python hooks: `black`, `isort`, `ruff` (or `flake8`), `check-ast`/`debug-statements`. Required Rust checks: `rustfmt` and `clippy` (via CI or a pre-commit hook wrapper).

- Developer steps (must be documented in CONTRIBUTING):
  - python: `pip install -U pre-commit` then `pre-commit install`
  - run checks locally before committing: `pre-commit run --all-files`

- CI must run the same checks (mirror command):
  - `pre-commit run --hook-stage manual --all-files` or call the individual commands (`black --check`, `isort --check-only`, `ruff check`, `cargo fmt -- --check`, `cargo clippy -- -D warnings`).

- Formatting & linting: Do not bypass formatting in PRs. If a formatting change is large, isolate it in a dedicated formatting-only PR.

## Do not

- Do not add project-wide exceptions to linters without a documented, timeboxed exemption and linked issue.

## Example (recommended `.pre-commit-config.yaml` snippet)

Include a minimal pre-commit configuration in the repo root; CI should call `pre-commit run --all-files` as a check.
