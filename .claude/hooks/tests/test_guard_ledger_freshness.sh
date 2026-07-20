#!/usr/bin/env bash
# Test for guard-ledger-freshness.sh — runs the hook against synthetic ledgers
# in an isolated temp ledger dir and asserts staleness detection + warn/block modes.
set -uo pipefail
HOOK="$(cd "$(dirname "$0")/.." && pwd)/guard-ledger-freshness.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/docs/superpowers/ledgers"
cd "$tmp"
git init -q && git commit -q --allow-empty -m init   # main branch exists

pass=0; fail=0
check() { if [ "$1" = "$2" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $3 (got '$1' want '$2')"; fi; }

# Case A: open ledger whose branch does not exist → stale warning, exit 0 (warn mode)
cat > docs/superpowers/ledgers/2026-01-01-ghost.md <<EOF
# Trunk Ledger — ghost — 2026-01-01
**Branch:** branch-that-does-not-exist-xyz   **Status:** open
EOF
out="$(LEDGER_DIR="$tmp/docs/superpowers/ledgers" bash "$HOOK" 2>&1)"; rc=$?
check "$rc" "0" "warn mode exits 0"
echo "$out" | grep -q "ghost" && check "yes" "yes" "warns about stale ledger" || check "no" "yes" "warns about stale ledger"

# Case B: same, but LEDGER_STRICT=block → exit 2
LEDGER_DIR="$tmp/docs/superpowers/ledgers" LEDGER_STRICT=block bash "$HOOK" >/dev/null 2>&1; rc=$?
check "$rc" "2" "block mode exits 2 on stale"

# Case C: converged ledger → no warning, exit 0
rm docs/superpowers/ledgers/2026-01-01-ghost.md
cat > docs/superpowers/ledgers/2026-01-02-done.md <<EOF
# Trunk Ledger — done — 2026-01-02
**Branch:** whatever   **Status:** converged
EOF
out="$(LEDGER_DIR="$tmp/docs/superpowers/ledgers" bash "$HOOK" 2>&1)"; rc=$?
check "$rc" "0" "converged ledger exits 0"
echo "$out" | grep -q "done" && check "no" "yes" "no warning for converged" || check "yes" "yes" "no warning for converged"

echo "PASS=$pass FAIL=$fail"
[ "$fail" -eq 0 ]
