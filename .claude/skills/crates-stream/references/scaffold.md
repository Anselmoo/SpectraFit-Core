# Scaffold reference — workspace layout, Cargo.toml, CI plumbing

Self-contained essentials for workspace scaffolding. Historical content
lives in git history under `.claude/skills/spectrafit-scaffold/`.

## Scope

- Workspace skeleton: root `Cargo.toml` `[workspace] members = [...]`.
- Per-crate manifests under `crates/<name>/Cargo.toml`.
- GitLab CI plumbing under `.gitlab/*.yml` (the `lint:rust` and
  `build:wheel` jobs).
- Worktree setup for branch-isolated experiments.

## crates-stream contract additions

1. **Serena first** for symbol-level edits, even in Cargo.toml refactors
   (read `Cargo.lock` and member lists with serena before mass-editing).
2. **Avoid touching `Cargo.lock` by hand** — let `cargo update -p <crate>`
   or `cargo build` resolve it; the lock churn hides real edits.
3. **DAG validity** is enforced by `pre-merge-dag.sh` (under the
   `verification` skill); a new crate must not introduce a cycle.

## Quick paths

- Workspace root: `Cargo.toml` (the `[workspace]` block lists members).
- Per-crate manifests: `crates/<name>/Cargo.toml`.
- CI scaffold: `.gitlab/*.yml` (the `lint:rust` and `build:wheel` jobs).
- Common scaffold targets: new model crate (see `rust-models.md`), new
  solver crate, new types-shared crate.

## Stuck-mode entry

Scaffold issues that reopen are usually circular-dependency or feature-
flag drift; curiosity sub-cycle via `cargo tree -e features` reveals
the loop almost every time.
