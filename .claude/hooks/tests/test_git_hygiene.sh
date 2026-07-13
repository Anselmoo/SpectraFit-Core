#!/usr/bin/env bash
# Test suite for git-hygiene.sh lib — hermetic tests using temp git repos.
# Each case builds a minimal git repo in a temp dir and asserts expected behaviour.
# Run with: bash .claude/hooks/tests/test_git_hygiene.sh
set -uo pipefail

LIB="$(cd "$(dirname "$0")/.." && pwd)/lib/git-hygiene.sh"

# Use temp files for counters so subshells can update them
_pass_f="$(mktemp)" _fail_f="$(mktemp)"
echo 0 > "$_pass_f"; echo 0 > "$_fail_f"

_inc_pass() { echo $(( $(cat "$_pass_f") + 1 )) > "$_pass_f"; }
_inc_fail() { echo $(( $(cat "$_fail_f") + 1 )) > "$_fail_f"; }

check() {
    local got="$1" want="$2" label="$3"
    if [ "$got" = "$want" ]; then
        _inc_pass
        echo "  ok: $label"
    else
        _inc_fail
        echo "  FAIL: $label (got '$got' want '$want')"
    fi
}
check_contains() {
    local haystack="$1" needle="$2" label="$3"
    if echo "$haystack" | grep -qF "$needle"; then
        _inc_pass
        echo "  ok: $label"
    else
        _inc_fail
        echo "  FAIL: $label (output did not contain '$needle')"
        echo "    actual: $haystack"
    fi
}
check_not_contains() {
    local haystack="$1" needle="$2" label="$3"
    if echo "$haystack" | grep -qF "$needle"; then
        _inc_fail
        echo "  FAIL: $label (output should NOT contain '$needle' but did)"
        echo "    actual: $haystack"
    else
        _inc_pass
        echo "  ok: $label"
    fi
}
check_dir_exists() {
    local dir="$1" label="$2"
    if [ -d "$dir" ]; then _inc_pass; echo "  ok: $label"
    else _inc_fail; echo "  FAIL: $label (dir gone: $dir)"; fi
}
check_dir_gone() {
    local dir="$1" label="$2"
    if [ ! -d "$dir" ]; then _inc_pass; echo "  ok: $label"
    else _inc_fail; echo "  FAIL: $label (dir still exists: $dir)"; fi
}

# ---------------------------------------------------------------------------
# Helper: create an isolated git repo with a configured identity
# ---------------------------------------------------------------------------
make_repo() {
    local dir="$1"
    git -C "$dir" init -q
    git -C "$dir" config user.email "test@test.local"
    git -C "$dir" config user.name "Test"
    git -C "$dir" commit -q --allow-empty -m "init"
}

# Master cleanup
_cleanup_dirs=()
_cleanup() {
    for d in "${_cleanup_dirs[@]+"${_cleanup_dirs[@]}"}"; do
        rm -rf "$d" 2>/dev/null || true
    done
    rm -f "$_pass_f" "$_fail_f"
}
trap _cleanup EXIT

echo "=== git-hygiene.sh lib tests ==="

# ---------------------------------------------------------------------------
# (h) GIT_HYGIENE_OFF=1 → whole thing is a no-op
# ---------------------------------------------------------------------------
echo "--- (h) GIT_HYGIENE_OFF=1 => no-op ---"
tmp_h="$(mktemp -d)"; _cleanup_dirs+=("$tmp_h")
make_repo "$tmp_h"
(
    cd "$tmp_h"
    GIT_HYGIENE_OFF=1 bash -c "source '$LIB' && check_branch_freshness && prune_worktrees" 2>"$tmp_h/h.err"
    echo $? > "$tmp_h/h.rc"
)
check "$(cat "$tmp_h/h.rc")" "0" "(h) OFF=1 exits 0"
check_not_contains "$(cat "$tmp_h/h.err")" "behind" "(h) OFF=1 no 'behind' warning"
check_not_contains "$(cat "$tmp_h/h.err")" "pruned" "(h) OFF=1 no 'pruned' output"

# ---------------------------------------------------------------------------
# (c) Up-to-date branch → no warning, exit 0
# ---------------------------------------------------------------------------
echo "--- (c) up-to-date branch => no warning ---"
tmp_c_remote="$(mktemp -d)"; tmp_c="$(mktemp -d)"
_cleanup_dirs+=("$tmp_c_remote" "$tmp_c")
make_repo "$tmp_c_remote"
git clone -q "$tmp_c_remote" "$tmp_c/clone"
git -C "$tmp_c/clone" config user.email "test@test.local"
git -C "$tmp_c/clone" config user.name "Test"
git -C "$tmp_c/clone" fetch -q origin 2>/dev/null || true
(
    cd "$tmp_c/clone"
    bash -c "source '$LIB' && check_branch_freshness" 2>"$tmp_c/c.err"
    echo $? > "$tmp_c/c.rc"
)
check "$(cat "$tmp_c/c.rc")" "0" "(c) up-to-date exits 0"
check_not_contains "$(cat "$tmp_c/c.err")" "behind" "(c) no 'behind' warning when up-to-date"

# ---------------------------------------------------------------------------
# (a) Branch behind upstream → warns
# ---------------------------------------------------------------------------
echo "--- (a) branch behind upstream => warns ---"
tmp_a_remote="$(mktemp -d)"; tmp_a="$(mktemp -d)"
_cleanup_dirs+=("$tmp_a_remote" "$tmp_a")
make_repo "$tmp_a_remote"
git clone -q "$tmp_a_remote" "$tmp_a/clone"
git -C "$tmp_a/clone" config user.email "test@test.local"
git -C "$tmp_a/clone" config user.name "Test"
# Add a commit to remote AFTER cloning so clone is behind
git -C "$tmp_a_remote" config user.email "test@test.local"
git -C "$tmp_a_remote" config user.name "Test"
git -C "$tmp_a_remote" commit -q --allow-empty -m "remote-ahead"
# Fetch in the clone so @{upstream} reflects the new remote commit
git -C "$tmp_a/clone" fetch -q origin 2>/dev/null || true
(
    cd "$tmp_a/clone"
    bash -c "source '$LIB' && check_branch_freshness" 2>"$tmp_a/a.err"
    echo $? > "$tmp_a/a.rc"
)
check "$(cat "$tmp_a/a.rc")" "0" "(a) warn mode exits 0 (never blocks)"
check_contains "$(cat "$tmp_a/a.err")" "behind" "(a) warns 'behind' when HEAD is behind upstream"

# ---------------------------------------------------------------------------
# (b) Base behind local main → warns
# ---------------------------------------------------------------------------
echo "--- (b) base behind main => warns ---"
tmp_b="$(mktemp -d)"; _cleanup_dirs+=("$tmp_b")
make_repo "$tmp_b"
git -C "$tmp_b" config user.email "test@test.local"
git -C "$tmp_b" config user.name "Test"
# Add extra commit to main, then branch from the initial commit
git -C "$tmp_b" commit -q --allow-empty -m "main-extra"
git -C "$tmp_b" checkout -q -b feature HEAD~1
(
    cd "$tmp_b"
    bash -c "source '$LIB' && check_branch_freshness" 2>"$tmp_b/b.err"
    echo $? > "$tmp_b/b.rc"
)
check "$(cat "$tmp_b/b.rc")" "0" "(b) warn mode exits 0"
check_contains "$(cat "$tmp_b/b.err")" "behind main" "(b) warns 'behind main' when base lags"

# ---------------------------------------------------------------------------
# (d) Offline/fetch failure → exits 0 silently (fail-open)
# ---------------------------------------------------------------------------
echo "--- (d) fetch failure => fail-open (exit 0, silent) ---"
tmp_d="$(mktemp -d)"; _cleanup_dirs+=("$tmp_d")
make_repo "$tmp_d"
git -C "$tmp_d" remote add origin "file:///nonexistent/path/that/does/not/exist"
(
    cd "$tmp_d"
    bash -c "source '$LIB' && check_branch_freshness" 2>"$tmp_d/d.err"
    echo $? > "$tmp_d/d.rc"
)
check "$(cat "$tmp_d/d.rc")" "0" "(d) fetch-fail exits 0 (fail-open)"
check_not_contains "$(cat "$tmp_d/d.err")" "error" "(d) no 'error' output on fetch fail"

# ---------------------------------------------------------------------------
# Shared worktree base for (e), (f), (g)
# ---------------------------------------------------------------------------
tmp_wt_base="$(mktemp -d)"; _cleanup_dirs+=("$tmp_wt_base")
make_repo "$tmp_wt_base"
git -C "$tmp_wt_base" config user.email "test@test.local"
git -C "$tmp_wt_base" config user.name "Test"

# Determine main branch name
wt_main_branch="main"
git -C "$tmp_wt_base" rev-parse --verify main >/dev/null 2>&1 || wt_main_branch="master"

# Create merged-branch: branch from HEAD, add commit, merge into main
git -C "$tmp_wt_base" checkout -q -b merged-branch
git -C "$tmp_wt_base" commit -q --allow-empty -m "merged-work"
git -C "$tmp_wt_base" checkout -q "$wt_main_branch"
git -C "$tmp_wt_base" merge -q --no-ff merged-branch -m "merge merged-branch"

# Create unmerged-branch: branch from main, add commit, do NOT merge
git -C "$tmp_wt_base" checkout -q -b unmerged-branch
git -C "$tmp_wt_base" commit -q --allow-empty -m "unmerged-work"
git -C "$tmp_wt_base" checkout -q "$wt_main_branch"

# ---------------------------------------------------------------------------
# (e) Worktree on merged branch → auto-removed
# ---------------------------------------------------------------------------
echo "--- (e) merged worktree => auto-removed ---"
wt_e="$(mktemp -d)"; _cleanup_dirs+=("$wt_e")
rmdir "$wt_e"  # git worktree add requires non-existent dir
git -C "$tmp_wt_base" worktree add -q "$wt_e" merged-branch
(
    cd "$tmp_wt_base"
    bash -c "source '$LIB' && prune_worktrees" 2>"$tmp_wt_base/e.err"
    echo $? > "$tmp_wt_base/e.rc"
)
check "$(cat "$tmp_wt_base/e.rc")" "0" "(e) exits 0"
check_contains "$(cat "$tmp_wt_base/e.err")" "removed" "(e) reports removal of merged worktree"
check_dir_gone "$wt_e" "(e) merged worktree dir was cleaned up"

# ---------------------------------------------------------------------------
# (f) Worktree with unmerged commits → flagged, NOT removed
# ---------------------------------------------------------------------------
echo "--- (f) unmerged worktree => flagged, not removed ---"
wt_f="$(mktemp -d)"; _cleanup_dirs+=("$wt_f")
rmdir "$wt_f"
git -C "$tmp_wt_base" worktree add -q "$wt_f" unmerged-branch
(
    cd "$tmp_wt_base"
    bash -c "source '$LIB' && prune_worktrees" 2>"$tmp_wt_base/f.err"
    echo $? > "$tmp_wt_base/f.rc"
)
check "$(cat "$tmp_wt_base/f.rc")" "0" "(f) exits 0"
check_contains "$(cat "$tmp_wt_base/f.err")" "flagged" "(f) flags unmerged worktree for review"
check_dir_exists "$wt_f" "(f) unmerged worktree dir still exists (not auto-removed)"
# Cleanup
git -C "$tmp_wt_base" worktree remove -f "$wt_f" 2>/dev/null || true

# ---------------------------------------------------------------------------
# (g) Locked worktree → untouched
# ---------------------------------------------------------------------------
echo "--- (g) locked worktree => untouched ---"
wt_g="$(mktemp -d)"; _cleanup_dirs+=("$wt_g")
rmdir "$wt_g"
git -C "$tmp_wt_base" worktree add -q "$wt_g" merged-branch
git -C "$tmp_wt_base" worktree lock "$wt_g"
(
    cd "$tmp_wt_base"
    bash -c "source '$LIB' && prune_worktrees" 2>"$tmp_wt_base/g.err"
    echo $? > "$tmp_wt_base/g.rc"
)
check "$(cat "$tmp_wt_base/g.rc")" "0" "(g) exits 0"
check_dir_exists "$wt_g" "(g) locked worktree was not removed"
# Cleanup
git -C "$tmp_wt_base" worktree unlock "$wt_g" 2>/dev/null || true
git -C "$tmp_wt_base" worktree remove -f "$wt_g" 2>/dev/null || true

# ---------------------------------------------------------------------------
# GIT_HYGIENE_PRUNE_OFF=1 → warn-only, no auto-remove even for merged
# ---------------------------------------------------------------------------
echo "--- (prune_off) GIT_HYGIENE_PRUNE_OFF=1 => warn-only, no auto-remove ---"
wt_p="$(mktemp -d)"; _cleanup_dirs+=("$wt_p")
rmdir "$wt_p"
git -C "$tmp_wt_base" worktree add -q "$wt_p" merged-branch
(
    cd "$tmp_wt_base"
    GIT_HYGIENE_PRUNE_OFF=1 bash -c "source '$LIB' && prune_worktrees" 2>"$tmp_wt_base/p.err"
    echo $? > "$tmp_wt_base/p.rc"
)
check "$(cat "$tmp_wt_base/p.rc")" "0" "(prune_off) exits 0"
check_dir_exists "$wt_p" "(prune_off) merged worktree NOT removed when PRUNE_OFF=1"
# Cleanup
git -C "$tmp_wt_base" worktree remove -f "$wt_p" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
pass=$(cat "$_pass_f"); fail=$(cat "$_fail_f")
echo "PASS=$pass FAIL=$fail"
[ "$fail" -eq 0 ]
