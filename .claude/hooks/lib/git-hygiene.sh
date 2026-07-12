#!/usr/bin/env bash
# git-hygiene.sh — shared library for git/worktree hygiene guards.
#
# Source this file; do NOT execute it directly.
#
# Exported functions:
#   check_branch_freshness  — warn if HEAD is behind upstream or base lags main
#   prune_worktrees         — prune/remove merged worktrees; flag unmerged/locked
#
# Environment knobs:
#   GIT_HYGIENE_OFF=1       → whole library no-ops (both functions silently exit 0)
#   GIT_HYGIENE_PRUNE_OFF=1 → prune_worktrees warns but never auto-removes anything
#
# Behaviour contract:
#   • NEVER block (never exit non-zero) — warn to stderr, always exit 0
#   • Fail-open: on any git error / offline / detached HEAD / not-a-repo, exit 0 silently
#   • Key off @{upstream} and local main — do NOT hardcode origin/main
#   (origin is a stale GitHub mirror in this repo; gitlab == local main is canonical)

# Guard against double-sourcing
if [[ "${_GIT_HYGIENE_LIB_LOADED:-}" == "1" ]]; then return 0; fi
_GIT_HYGIENE_LIB_LOADED=1

# ---------------------------------------------------------------------------
# check_branch_freshness
#
# 1. git fetch --quiet (timeout 10 s, fail-open)
# 2. If HEAD is behind @{upstream}: warn "N commits behind <upstream>; pull first"
# 3. If merge-base(HEAD, main) is behind local main: warn "base is M commits behind main; rebase"
# Skips cleanly when: no upstream, detached HEAD, no 'main' branch, not a repo.
# ---------------------------------------------------------------------------
check_branch_freshness() {
    # Global kill switch
    if [[ "${GIT_HYGIENE_OFF:-0}" == "1" ]]; then return 0; fi

    # Must be inside a git repo
    git rev-parse --git-dir >/dev/null 2>&1 || return 0

    # ---- fetch (fail-open: any error → continue) -------------------------
    # Use a short timeout so offline sessions don't stall.
    if command -v timeout >/dev/null 2>&1; then
        timeout 10 git fetch --quiet 2>/dev/null || true
    else
        # macOS gtimeout or just skip; still fail-open
        git fetch --quiet 2>/dev/null || true
    fi

    # ---- check (a): HEAD behind @{upstream} ------------------------------
    local upstream
    upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null)" || upstream=""

    if [[ -n "$upstream" ]]; then
        local behind
        behind="$(git rev-list --count 'HEAD..@{upstream}' 2>/dev/null)" || behind=""
        if [[ -n "$behind" && "$behind" -gt 0 ]]; then
            echo "git-hygiene: HEAD is $behind commit(s) behind $upstream; pull first (GIT_HYGIENE_OFF=1 to silence)" >&2
        fi
    fi

    # ---- check (b): merge-base(HEAD, main) behind local main -------------
    # Only when a local 'main' branch exists.
    local main_branch="main"
    if ! git rev-parse --verify --quiet "$main_branch" >/dev/null 2>&1; then
        # Try 'master' as a fallback
        if git rev-parse --verify --quiet "master" >/dev/null 2>&1; then
            main_branch="master"
        else
            return 0  # no main/master → skip
        fi
    fi

    # Detached HEAD → skip the base-check (no branch to compare)
    local current_branch
    current_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || return 0
    if [[ "$current_branch" == "HEAD" ]]; then return 0; fi

    # If we ARE on main, nothing to compare
    if [[ "$current_branch" == "$main_branch" ]]; then return 0; fi

    local merge_base main_head
    merge_base="$(git merge-base HEAD "$main_branch" 2>/dev/null)" || return 0
    main_head="$(git rev-parse "$main_branch" 2>/dev/null)" || return 0

    if [[ "$merge_base" != "$main_head" ]]; then
        local behind_main
        behind_main="$(git rev-list --count "$merge_base..$main_branch" 2>/dev/null)" || behind_main="?"
        echo "git-hygiene: base is $behind_main commit(s) behind main; consider rebasing to work on the latest (GIT_HYGIENE_OFF=1 to silence)" >&2
    fi

    return 0
}

# ---------------------------------------------------------------------------
# prune_worktrees
#
# Iterates `git worktree list --porcelain`:
#   • `git worktree prune` first (cleans up registrations whose dirs are gone)
#   • For each non-current, non-locked worktree:
#       - branch merged into main → `git worktree remove` (unless PRUNE_OFF=1)
#       - branch NOT merged → flagged for review (never auto-removed)
#       - locked → untouched
# Prints summary: "pruned N, removed M merged, flagged K for review"
# ---------------------------------------------------------------------------
prune_worktrees() {
    # Global kill switch
    if [[ "${GIT_HYGIENE_OFF:-0}" == "1" ]]; then return 0; fi

    # Must be inside a git repo
    git rev-parse --git-dir >/dev/null 2>&1 || return 0

    local prune_off="${GIT_HYGIENE_PRUNE_OFF:-0}"

    # Resolve the current worktree path (to avoid touching it)
    local current_wt
    current_wt="$(git rev-parse --show-toplevel 2>/dev/null)" || return 0

    # Determine main branch name
    local main_branch="main"
    if ! git rev-parse --verify --quiet "$main_branch" >/dev/null 2>&1; then
        if git rev-parse --verify --quiet "master" >/dev/null 2>&1; then
            main_branch="master"
        else
            main_branch=""
        fi
    fi

    # Step 1: prune registrations whose directory is gone
    local pruned_count=0
    git worktree prune 2>/dev/null && pruned_count=1 || true

    # Step 2: parse worktree list
    local removed=0 flagged=0

    # Resolve the primary (main) worktree path — always first in porcelain output
    local primary_wt
    primary_wt="$(git worktree list --porcelain 2>/dev/null | awk '/^worktree /{print substr($0,10); exit}')" || primary_wt=""

    _process_worktree() {
        local path="$1" branch="$2" locked="$3"

        # Skip the current worktree (where we're running from)
        if [[ "$path" == "$current_wt" ]]; then return; fi
        # Skip the primary/main worktree (first entry — never auto-remove it)
        if [[ "$path" == "$primary_wt" ]]; then return; fi
        # Skip bare worktrees (no branch)
        if [[ -z "$branch" ]]; then return; fi
        # Skip locked worktrees
        if [[ -n "$locked" ]]; then return; fi

        # Determine if branch is merged into main
        local is_merged=0
        if [[ -n "$main_branch" ]]; then
            if git branch --merged "$main_branch" --format='%(refname:short)' 2>/dev/null | grep -Fxq "$branch" 2>/dev/null; then
                # Ensure it's not main itself
                if [[ "$branch" != "$main_branch" ]]; then
                    is_merged=1
                fi
            fi
        fi

        if [[ "$is_merged" == "1" ]]; then
            if [[ "$prune_off" == "1" ]]; then
                echo "git-hygiene: merged worktree '$path' (branch: $branch) — would auto-remove (GIT_HYGIENE_PRUNE_OFF=1, skipping)" >&2
                flagged=$((flagged+1))
            else
                if git worktree remove --force "$path" 2>/dev/null; then
                    echo "git-hygiene: removed merged worktree '$path' (branch: $branch)" >&2
                    removed=$((removed+1))
                else
                    echo "git-hygiene: could not remove worktree '$path' — flagged for manual review" >&2
                    flagged=$((flagged+1))
                fi
            fi
        else
            # Unmerged — flag only
            echo "git-hygiene: worktree '$path' (branch: $branch) has unmerged commits — flagged for review (not auto-removed)" >&2
            flagged=$((flagged+1))
        fi
    }

    # Parse `git worktree list --porcelain` output
    # Format: blank-line-separated stanzas with keys: worktree, HEAD, branch, bare, locked, prunable
    local _path="" _branch="" _locked=""
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ -z "$line" ]]; then
            # End of stanza — process it
            if [[ -n "$_path" ]]; then
                _process_worktree "$_path" "$_branch" "$_locked"
            fi
            _path=""; _branch=""; _locked=""
            continue
        fi
        case "$line" in
            worktree\ *)  _path="${line#worktree }"; _branch=""; _locked="" ;;
            branch\ *)    _branch="${line#branch refs/heads/}" ;;
            locked*)      _locked="yes" ;;
        esac
    done < <(git worktree list --porcelain 2>/dev/null; echo "")
    # Process last stanza if file doesn't end with blank line
    if [[ -n "$_path" ]]; then
        _process_worktree "$_path" "$_branch" "$_locked"
    fi

    echo "git-hygiene: worktree sweep — pruned stale registrations, removed $removed merged, flagged $((flagged)) for review" >&2
    return 0
}
