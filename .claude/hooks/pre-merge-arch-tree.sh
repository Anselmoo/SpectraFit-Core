#!/usr/bin/env bash
# Fail locally when docs/contributor-guide/architecture.md's embedded directory
# tree is stale, so it cannot reach a runner.
#
# WHY THIS EXISTS. `lint:python` (.gitlab/20-lint.yml) regenerates that tree and
# fails on any drift. Nothing checked it client-side, so the only signal was a
# red pipeline several minutes after a push — and because ANY file added or
# removed at depth <= 2 changes the tree, that happened repeatedly: pipelines
# 366818, 366826, 366889 and 366934, each fixed by hand, each recurring the next
# time a file was added. A check that only runs after the push is a check that
# teaches nothing.
#
# The regeneration is deterministic and takes a couple of seconds, so it runs
# unconditionally rather than trying to guess from a `files:` pattern which
# changes could affect the tree — "added scripts/vendored_assets.toml" is not a
# pattern anyone would think to write, and it was one of the four failures.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

TARGET="docs/contributor-guide/architecture.md"

# Regenerate in place. `rrt tree --snapshot` also rewrites .rrt/tree.lock.toml,
# which is the documented refresh command (CLAUDE.md) and is why the upstream
# rrt-tree-check hook is deliberately NOT wired — it full-depth-scans the same
# lock file this depth-2 workflow owns, and the two fight over it.
uv run --no-sync rrt tree --root . --max-depth 2 --snapshot >/dev/null
uv run --no-sync python scripts/render_architecture_tree.py >/dev/null

if ! git diff --quiet -- "$TARGET"; then
  echo "ERROR ${TARGET}'s directory tree was stale and has been regenerated." >&2
  echo >&2
  git --no-pager diff --stat -- "$TARGET" >&2
  echo >&2
  echo "The file is now correct in your working tree — stage it and retry:" >&2
  echo "    git add ${TARGET}" >&2
  echo >&2
  echo "This is the same check .gitlab/20-lint.yml runs; failing here saves a" >&2
  echo "round-trip to the runner." >&2
  exit 1
fi

exit 0
