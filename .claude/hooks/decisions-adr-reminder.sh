#!/usr/bin/env bash
# decisions-adr-reminder.sh — PreToolUse(Bash) hook, gated on `git commit`.
#
# History: originally an unconditional Stop-hook `prompt` firing on EVERY
# turn (blocked development). Fixed once (2026-08-08) to skip idle/clean
# turns and comment-only diffs — but a Stop hook still re-fires on every
# single turn for as long as ANY matched path stays dirty, which for a
# real multi-hour session means dozens of identical re-firings burning
# tokens even when nothing changed between them. Fixed again (2026-08-09)
# to skip linked worktrees. 2026-08-10: moved the whole check from Stop to
# PreToolUse(Bash), gated on the Bash command actually being `git commit`
# — the one moment this reminder is substantively useful, and one that
# happens at most a handful of times per session instead of every turn.
#
# Also narrowed the check from "the whole dirty working tree" to "what's
# actually staged for THIS commit" (`git diff --cached`), since the old
# whole-tree check would have wrongly blocked a scoped, unrelated commit
# just because some OTHER unstaged file elsewhere in the tree happens to
# touch a matched path — a real bug, not hypothetical: it would have fired
# on every one of three clean, scoped commits made in the session that
# prompted this rewrite, since ~50 unrelated dirty files sat in the tree
# throughout. `-a`/`--all` is handled by falling back to the whole
# working-tree diff, since that's what those flags actually commit.
#
# Self-referential gotcha discovered while writing this: matching the
# trigger phrase anywhere in the raw command TEXT (not just as a real
# invocation) means any command whose payload merely *discusses* this
# hook — a commit message describing it, a python heredoc writing this
# very file — contains that literal two-word phrase and falsely
# self-triggers. Fixed by requiring the phrase to start an actual shell
# statement (right after a separator, not buried mid-line in a comment or
# heredoc body) before treating it as a real invocation.
#
# if/else matching: only block the commit (exit 2, feeds the message back
# to the model) when ALL of these hold:
#   1. a real invocation of the two-word git subcommand starts a shell
#      statement in tool_input.command (same stdin-JSON pattern as
#      guard-branch-freshness.sh), AND
#   2. cwd is NOT a linked worktree (git-dir == git-common-dir only in the
#      primary checkout; WIP in a worktree hasn't landed on main yet, so
#      an ADR belongs at merge time), AND
#   3. what's about to be committed touches a decision-worthy area
#      (crates / spectrafit_core / oracles / web / CI), AND
#   4. DECISIONS.md is NOT itself among the changes being committed, AND
#   5. at least one matched file's diff touches a real code/config line,
#      not just comments/docstrings/blank lines (see is_trivial_diff.py
#      below).
# In every other case — not that invocation, a worktree, nothing staged,
# nothing matched, DECISIONS.md already included, or a comment/docstring-
# only diff — exit 0 silently (no block, no message, no token cost).
#
# ADR_REMINDER_OFF=1 → unconditional no-op escape hatch (set in your own
# shell before invoking Claude Code; a hook validates the command before
# any part of it — including an inline VAR=val prefix — actually runs, so
# this must be set in the ambient environment, not embedded in the
# triggering command itself).
set -uo pipefail

if [[ "${ADR_REMINDER_OFF:-0}" == "1" ]]; then exit 0; fi

root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$root" || exit 0

# Skip entirely inside a linked worktree: `git rev-parse --git-dir` there
# points at .git/worktrees/<name>, while `--git-common-dir` always points at
# the shared .git. In the primary checkout the two are identical.
git_dir="$(cd "$(git rev-parse --git-dir 2>/dev/null)" 2>/dev/null && pwd)"
git_common_dir="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd)"
[ -n "$git_dir" ] && [ -n "$git_common_dir" ] && [ "$git_dir" != "$git_common_dir" ] && exit 0

# Read the PreToolUse JSON payload from stdin (same pattern as
# guard-branch-freshness.sh / guard-test-hygiene.sh).
_tmpf="$(mktemp)"
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

HOOK_STDIN_FILE="$_tmpf" python3 - <<'PYEOF'
import json, os, re, sys

try:
    with open(os.environ["HOOK_STDIN_FILE"], encoding="utf-8") as fh:
        payload = json.load(fh)
except Exception:
    sys.exit(0)

cmd = (payload.get("tool_input") or {}).get("command", "")

# Only treat the phrase as a real invocation when it starts a shell
# statement (right after ';', '&&', '||', a newline, or at the very start
# of cmd) -- not wherever the two words happen to appear in the text. See
# the header comment: a naive whole-blob search self-triggers on any
# command whose payload merely discusses this hook.
target = re.compile(r"\s*git\s+commit\b")
statements = re.split(r"(?:;|\n|&&|\|\|)", cmd)
commit_stmt = next((s for s in statements if target.match(s)), None)
if commit_stmt is None:
    sys.exit(0)

# Only scan the actual CLI-flag region -- from right after the subcommand
# up to the first quote -- for -a/--all, not the rest of the statement
# (which may contain a -m "message body" mentioning those flags in prose).
m = re.search(r"git\s+commit\b", commit_stmt)
flag_region = re.split(r"['\"]", commit_stmt[m.end():], maxsplit=1)[0]

# 42 = plain invocation (check what's staged). 43 = `-a`/`--all` (check the
# whole working tree, since that's what actually gets committed).
sys.exit(43 if re.search(r"(^|\s)-[a-zA-Z]*a[a-zA-Z]*(\s|$)|--all\b", flag_region) else 42)
PYEOF

py_rc=$?
[ "$py_rc" -ne 42 ] && [ "$py_rc" -ne 43 ] && exit 0
commit_all=0
[ "$py_rc" -eq 43 ] && commit_all=1

if [ "$commit_all" -eq 1 ]; then
  changed="$(git status --porcelain 2>/dev/null | sed 's/^...//')"
else
  changed="$(git diff --cached --name-only 2>/dev/null)"
fi
[ -z "$changed" ] && exit 0  # nothing to commit (git itself will say so)

# DECISIONS.md is part of this commit → assume the decision is recorded.
printf '%s\n' "$changed" | grep -qx 'DECISIONS.md' && exit 0

# Decision-worthy areas: behavioural/architectural surfaces. Doc/skill/test-only
# edits do NOT match, so they never trigger the reminder.
matched="$(printf '%s\n' "$changed" | grep -E '^(crates/|python/spectrafit_core/|python/oracles/|web/|\.github/workflows/)')"
[ -z "$matched" ] && exit 0

# Diff-content check: skip if every matched file's diff (staged, or working
# tree under -a) is comment/docstring/blank-only. Best-effort heuristic (not
# a full parser) — false negatives (treating a real change as trivial) are
# acceptable for a nag hook; a human/model always reviews the actual diff
# before deciding on an ADR.
non_trivial="$(python3 - "$matched" "$commit_all" <<'PYEOF' 2>/dev/null
import subprocess, sys

files = [f for f in sys.argv[1].splitlines() if f]
commit_all = sys.argv[2] == "1"

def docstring_mask(text):
    # 1-indexed line numbers inside -- or entirely spanned by -- a
    # triple-quoted string, via a simple per-line toggle on triple-double or
    # triple-single quote sequences.
    inside = False
    mask = set()
    for i, line in enumerate(text.splitlines(), 1):
        started_inside = inside
        n = line.count('"""') + line.count("'''")
        if n % 2 == 1:
            inside = not inside
            mask.add(i)
        elif n > 0:
            # Even, nonzero count: the string opens and closes on this same
            # line (e.g. a one-line docstring `"""Summary."""`) -- the whole
            # line is string content, not a toggle, but still not real code.
            mask.add(i)
        if started_inside:
            mask.add(i)
    return mask

def file_at_rev(path, rev):
    try:
        return subprocess.run(
            ["git", "show", f"{rev}:{path}"],
            capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return ""

def new_content(path):
    # What will actually land in the commit: the working tree under -a/--all,
    # the index (staged content) otherwise -- which can differ from the
    # working tree if the file was edited again after `git add`.
    if commit_all:
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""
    # NOT file_at_rev(path, ":") -- that builds "git show" + f"{rev}:{path}"
    # with rev=":" -> "::path" (double colon), which git rejects outright as
    # an ambiguous/invalid ref, silently returning "" via the except clause
    # below. An empty new_text makes docstring_mask() return an empty set, so
    # EVERY staged docstring-only insertion looks like non-docstring content
    # and the whole trivial-diff exemption silently stops working for staged
    # commits -- caught by testing a real docstring insertion before trusting
    # this rewrite, not found any other way.
    try:
        return subprocess.run(
            ["git", "show", f":{path}"],
            capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return ""

def is_comment_line(stripped, path):
    if stripped == "":
        return True
    if stripped in ('"""', "'''"):
        return True
    if path.endswith((".py",)):
        return stripped.startswith("#")
    if path.endswith((".rs", ".ts", ".tsx")):
        return stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*")
    if path.endswith((".yml", ".yaml")):
        return stripped.startswith("#")
    return False  # unknown extension: never treat as trivial

def code_prefix(content, path):
    # Best-effort: the code portion before a trailing inline comment marker
    # (e.g. `erfcx,  # scaled erfc...`). Not string-literal aware -- a '#' or
    # '//' inside a string literal is a rare false split, acceptable for a
    # best-effort nag heuristic (see module docstring).
    if path.endswith((".py", ".yml", ".yaml")):
        idx = content.find("#")
    elif path.endswith((".rs", ".ts", ".tsx")):
        idx = content.find("//")
    else:
        idx = -1
    return content[:idx].rstrip() if idx != -1 else content.rstrip()

def diff_is_trivial(path):
    diff_cmd = ["git", "diff", "-U0", "--", path] if commit_all else ["git", "diff", "--cached", "-U0", "--", path]
    try:
        diff = subprocess.run(diff_cmd, capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return False
    if not diff:
        return True  # nothing changed (e.g. mode-only) -- not our concern

    old_text = file_at_rev(path, "HEAD")
    new_text = new_content(path)
    old_mask = docstring_mask(old_text)
    new_mask = docstring_mask(new_text)

    old_line = new_line = 0
    # A '-' line with real (non-comment/docstring) content is held here until
    # we see what follows: if the very next diff line is a matching '+' whose
    # code prefix (content before a trailing inline comment) is identical,
    # this is a single-line inline-comment-only edit -- e.g.
    # `erfcx,  # exp(x²)·erfc(x)` -> `erfcx,  # exp(x^2)*erfc(x)` -- and both
    # lines are trivial together even though neither is trivial alone.
    pending_removed = None
    for raw in diff.splitlines():
        if raw.startswith("@@"):
            if pending_removed is not None:
                return False
            # @@ -a,b +c,d @@
            try:
                parts = raw.split("@@")[1].strip().split()
                old_line = int(parts[0].split(",")[0].lstrip("-")) - 1
                new_line = int(parts[1].split(",")[0].lstrip("+")) - 1
            except (IndexError, ValueError):
                return False
            continue
        if raw.startswith("---") or raw.startswith("+++"):
            continue
        if raw.startswith("-"):
            old_line += 1
            content = raw[1:]
            if old_line in old_mask or is_comment_line(content.strip(), path):
                if pending_removed is not None:
                    return False
                continue
            if pending_removed is not None:
                return False  # two unresolved removals in a row
            pending_removed = content
            continue
        if raw.startswith("+"):
            new_line += 1
            content = raw[1:]
            if new_line in new_mask or is_comment_line(content.strip(), path):
                if pending_removed is not None:
                    return False
                continue
            if pending_removed is not None:
                if code_prefix(pending_removed, path) == code_prefix(content, path):
                    pending_removed = None
                    continue
                return False
            return False
    if pending_removed is not None:
        return False
    return True

non_trivial = [f for f in files if not diff_is_trivial(f)]
print("\n".join(non_trivial))
PYEOF
)"
py_status=$?

# If the python helper failed for any reason (no python3, unexpected error),
# fall back to the old path-only behaviour rather than silently under-warning.
if [ "$py_status" -ne 0 ]; then
  non_trivial="$matched"
fi

[ -z "$non_trivial" ] && exit 0   # every matched file's diff is comment/docstring-only

echo "About to commit with DECISIONS.md not updated, but the changes touch a \
behavioural/architectural surface (crates / spectrafit_core / oracles / web / CI). \
If this change embodies an architectural or behavioural decision, append an ADR to \
DECISIONS.md — top entry '## [YYYY-MM-DD] <Title>' with **Context**/**Decision**/\
**Rationale**/**Trade-offs**, naming the files/symbols — then re-run the commit. \
Skip for trivial work (typos, comments/docstrings, dep bumps, pure refactors, \
read-only investigation): set ADR_REMINDER_OFF=1 in your shell to bypass." >&2
exit 2
