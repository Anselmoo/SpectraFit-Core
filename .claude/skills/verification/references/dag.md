# DAG reference — Rust crate dependency validation

Self-contained essentials. Historical specialist content lives in git
history under `.claude/skills/dag-validator/`.

## What this validates

The Rust workspace under `crates/` has architectural constraints:

1. **No cycles** in the dependency graph.
2. **No invalid cross-dependencies** (e.g. `spectrafit-types` must not
   depend on `spectrafit-solver` — types is a leaf).
3. **Workspace consistency** — every member listed in the root
   `Cargo.toml` `[workspace]` block exists and builds.

## How to run

Pre-merge gate: `.claude/hooks/pre-merge-dag.sh` runs the validation
on any branch about to merge. Local dev:

```bash
cargo tree --workspace --edges normal --format "{p}" > /tmp/dag.txt
# inspect; or use a dot-graph generator if needed
```

For visualization, a generator script may exist; check
`tools/dag_viz.py` via `mcp__serena__find_symbol`.

## Common failures and fixes

- **New cycle introduced** — usually a new crate added a
  back-edge to a higher-level crate. Move the shared types down to
  `spectrafit-types`.
- **Member missing** — added a crate dir but forgot the
  `[workspace] members = [...]` entry.
- **Feature-flag drift** — `cargo tree -e features` reveals
  cycle-via-features.

## Stuck-mode entry

A DAG failure that reopens is usually feature-flag drift —
`cargo tree -e features` is the curiosity sub-cycle tool.
