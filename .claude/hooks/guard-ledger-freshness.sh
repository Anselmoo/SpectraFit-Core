#!/usr/bin/env bash
# SessionStart reaper for trunk ledgers (semantic-debugging skill).
#
# Scans docs/superpowers/ledgers/ for OPEN ledgers whose trunk branch is already
# merged into main, deleted, or absent — the "no death date" leftover the ledger
# lifecycle exists to prevent. Warn by default (exit 0); LEDGER_STRICT=block → exit 2.
#
# A ledger declares two parseable fields (on one line, grepped independently):
#   **Branch:** <git-branch>   **Status:** open|converged
set -uo pipefail

root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$root" || exit 0
LEDGER_DIR="${LEDGER_DIR:-docs/superpowers/ledgers}"
[ -d "$LEDGER_DIR" ] || exit 0

findings=0
for f in "$LEDGER_DIR"/*.md; do
  [ -e "$f" ] || continue
  case "$(basename "$f")" in README.md) continue;; esac
  status="$(grep -oiE '\*\*Status:\*\*[[:space:]]*[a-z]+' "$f" | head -1 | grep -oiE '(open|converged)' | tr 'A-Z' 'a-z')"
  [ "$status" = "open" ] || continue
  branch="$(grep -oE '\*\*Branch:\*\*[[:space:]]*[^[:space:]]+' "$f" | head -1 | sed -E 's/.*\*\*Branch:\*\*[[:space:]]*//')"
  [ -n "$branch" ] || continue
  stale=""
  if ! git rev-parse --verify --quiet "$branch" >/dev/null 2>&1; then
    stale="trunk branch '$branch' no longer exists (merged or deleted)"
  elif git branch --merged main --format='%(refname:short)' 2>/dev/null | grep -Fxq "$branch" && [ "$branch" != "main" ]; then
    stale="trunk branch '$branch' is merged into main"
  fi
  if [ -n "$stale" ]; then
    findings=$((findings+1))
    echo "stale ledger: $f — $stale. Reap it: delete the file and graduate its decision to DECISIONS.md." >&2
  fi
  # DoD-vs-reality: claims merged but branch not merged.
  if grep -qiE '^\- \[x\][[:space:]].*merged to main' "$f"; then
    if [ "$branch" != "main" ] && ! git branch --merged main --format='%(refname:short)' 2>/dev/null | grep -Fxq "$branch"; then
      findings=$((findings+1))
      echo "ledger lies: $f marks 'merged to main' done, but '$branch' is not merged." >&2
    fi
  fi
done

[ "$findings" -eq 0 ] && exit 0
if [ "${LEDGER_STRICT:-warn}" = "block" ]; then exit 2; fi
exit 0
