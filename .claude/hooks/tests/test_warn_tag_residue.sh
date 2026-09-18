#!/usr/bin/env bash
# Test for warn-tag-residue.sh (GOV-14) — runs the hook against a synthetic
# git repo with staged fixtures and asserts it (a) fires on newly staged
# internal tracking tags, (b) stays silent on held-out prose that looks
# similar but isn't a tag, and (c) stays silent on a clean staged diff.
set -uo pipefail
HOOK="$(cd "$(dirname "$0")/.." && pwd)/warn-tag-residue.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cd "$tmp" || exit 1
git init -q
git config user.email test@example.com
git config user.name test
git commit -q --allow-empty -m init

pass=0; fail=0
check() { if [ "$1" = "$2" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $3 (got '$1' want '$2')"; fi; }

# Case A: seeded new tags of all four kinds → hook fires (non-empty output),
# still exits 0 (warn-only, never blocks).
cat > fixture_a.py <<'EOF'
# Fixed per EF-PY-99 (Cycle 42): guard against G99 regression, see Plan Z9.
def f():
    return 1
EOF
git add fixture_a.py
out="$(bash "$HOOK" 2>&1)"; rc=$?
check "$rc" "0" "case A: never blocks"
echo "$out" | grep -q "EF-PY-99" && check "yes" "yes" "case A: flags EF-PY-99" || check "no" "yes" "case A: flags EF-PY-99"
echo "$out" | grep -q "Cycle 42" && check "yes" "yes" "case A: flags Cycle 42" || check "no" "yes" "case A: flags Cycle 42"
echo "$out" | grep -q "G99" && check "yes" "yes" "case A: flags G99" || check "no" "yes" "case A: flags G99"
echo "$out" | grep -q "Plan Z9" && check "yes" "yes" "case A: flags Plan Z9" || check "no" "yes" "case A: flags Plan Z9"
git reset -q fixture_a.py
rm -f fixture_a.py

# Case B: held-out prose that resembles a tag but is not one — must stay
# silent. "Plan your day" (no second capital+digit), "cycle 3" (lowercase c,
# not the tracking-tag spelling), "G16 basis set" (G+2digits IS still caught
# by design — G\d{2} has no semantic disambiguator; document that below
# instead of asserting silence on it, so this test can't quietly rot into
# asserting a false expectation).
cat > fixture_b.py <<'EOF'
# Plan your day before the fit; the optimizer needs a warm start.
# Run a second cycle 3 refinement pass if residuals stay high.
EOF
git add fixture_b.py
out="$(bash "$HOOK" 2>&1)"; rc=$?
check "$rc" "0" "case B: never blocks"
check "$out" "" "case B: silent on non-tag prose"
git reset -q fixture_b.py
rm -f fixture_b.py

# Case C: clean repo, nothing staged → silent, exit 0.
out="$(bash "$HOOK" 2>&1)"; rc=$?
check "$rc" "0" "case C: exits 0 on clean diff"
check "$out" "" "case C: silent on clean diff"

echo "PASS=$pass FAIL=$fail"
[ "$fail" -eq 0 ]
