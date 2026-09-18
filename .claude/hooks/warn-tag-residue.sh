#!/usr/bin/env bash
# [GIT PRE-COMMIT · WARNING ONLY, NEVER BLOCKS]
#
# GOV-14: internal tracking identifiers (an audit-cycle tag, a scan-generation
# label, a lettered/numbered internal plan) do not belong in shipped source
# comments — they mean nothing to a reader without the (private, ephemeral)
# tracking doc they came from. Two dedicated sweep plans each closed their own
# enumerated list of these and 23 tags across 21 files still survived,
# because each sweep fixed a list, not the underlying habit. This hook flags
# the habit going forward instead of re-sweeping the backlog a third time.
#
# Scope is deliberately narrow: only lines ADDED by the currently staged diff
# (a `git diff --cached` `+` line), in `.py`/`.rs`/`.yml`/`.yaml` files. The
# 23 pre-existing tags are NOT re-flagged here — re-litigating them on every
# unrelated commit would make this hook noise, not signal, and the goal is to
# stop a third sweep from being necessary, not to force a cleanup today.
#
# Pattern (verified against the live tree — zero false positives found
# scanning every current EF-*/Cycle */Plan */G\d{2} occurrence in .py/.rs/.yml
# before this hook was added; see .claude/hooks/tests/test_warn_tag_residue.sh
# for held-out prose that must NOT be flagged, e.g. "G16 basis set", "Plan
# your day", ordinary "cycle 3 of the loop" without a capital C):
#   EF-[A-Z]+-[0-9]+   e.g. EF-RUST-02, EF-PY-10
#   Cycle [0-9]+       e.g. Cycle 5, Cycle 30L (trailing letter allowed)
#   Plan [A-Z][0-9]?   e.g. Plan C, Plan C2 (single capital, optional digit —
#                      NOT "Plan your", which needs a second capital letter)
#   G[0-9]{2}\b        e.g. G27, G26 (exactly 2 digits, word-bounded — does
#                      NOT match a 3+ digit run like a version "G160")
#
# See warn-grey-comments.sh for the same "advisory, exit 0 unconditional"
# shape and rationale: whether a tag is genuinely still load-bearing (e.g. an
# open cross-reference to an active ledger) or pure residue is a judgement
# call only the author can make well.
set -uo pipefail

DIFF="$(git diff --cached --unified=0 -- '*.py' '*.rs' '*.yml' '*.yaml' 2>/dev/null)"
[ -z "$DIFF" ] && exit 0

# NOTE: the script body must come from a FILE, not a heredoc piped alongside
# `python3 -`. `printf ... | python3 - <<'PYEOF'` looks like "pipe the diff in,
# read the script from the heredoc" but a heredoc redirect on the same command
# as a pipe wins over the pipe for stdin — `python3 -` would read the heredoc
# as its *script*, leaving nothing on stdin for the script itself to read.
_pyf=$(mktemp)
trap 'rm -f "$_pyf"' EXIT
cat > "$_pyf" <<'PYEOF'
import re
import sys

# Loaded once; the pattern is the hook's contract with the rest of the repo —
# keep it here (not in a shared module) since, unlike GOV-07, no PreToolUse
# hook needs the same check today.
PATTERN = re.compile(r"EF-[A-Z]+-[0-9]+|Cycle [0-9]+|Plan [A-Z][0-9]?|G[0-9]{2}\b")

current_file = None
found: list[tuple[str, str]] = []
for line in sys.stdin:
    line = line.rstrip("\n")
    if line.startswith("+++ "):
        # "+++ b/path/to/file" (or "+++ /dev/null" for a deletion)
        path = line[4:]
        current_file = path[2:] if path.startswith("b/") else None
        continue
    if not line.startswith("+") or line.startswith("+++"):
        continue
    added = line[1:]
    m = PATTERN.search(added)
    if m and current_file:
        found.append((current_file, added.strip()))

for path, text in found:
    print(f"{path}: {text}")
PYEOF
MATCHES="$(printf '%s\n' "$DIFF" | python3 "$_pyf")"

if [ -n "$MATCHES" ]; then
    printf '\n\033[33m! tag residue\033[0m — newly staged line(s) carry an internal tracking tag\n'
    printf '  (EF-XX-NN / Cycle N / Plan X[N] / GNN) that a shipped comment should not:\n\n'
    printf '%s\n' "$MATCHES" | sed 's/^/    /'
    printf '\n  These tags mean nothing outside the (private, ephemeral) tracking doc they\n'
    printf '  came from. If this is genuinely still load-bearing (an open cross-reference\n'
    printf '  to an active ledger), leave it; otherwise drop the tag and keep the prose.\n'
    printf '  (advisory only — this hook never blocks a commit)\n\n'
fi

exit 0
