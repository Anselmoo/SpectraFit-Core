#!/usr/bin/env bash
# git-hygiene-session.sh — SessionStart hook.
#
# Sources the git-hygiene lib and runs:
#   1. check_branch_freshness — warn if HEAD is behind upstream or base lags main
#   2. prune_worktrees        — prune/remove merged worktrees; flag unmerged/locked
#
# Both functions are warn-only (exit 0); no blocking.
# GIT_HYGIENE_OFF=1 → entire script no-ops.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/git-hygiene.sh
source "$SCRIPT_DIR/lib/git-hygiene.sh"

check_branch_freshness
prune_worktrees
