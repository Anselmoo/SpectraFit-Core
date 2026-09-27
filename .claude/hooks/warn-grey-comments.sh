#!/usr/bin/env bash
# [GIT PRE-COMMIT · WARNING ONLY, NEVER BLOCKS]
#
# Flags staged Python files carrying comment blocks that sit where a docstring
# belongs — before a module's first statement, before a `def`/`class`, or as a
# declaration's first body line. Those blocks render greyed-out in an editor and
# are invisible to `help()`, mkdocstrings, and the generated API reference, so
# documentation written that way reaches nobody.
#
# WHY IT ONLY WARNS. The decision is a judgement call: some leading comments are
# implementation notes that are correctly comments, and only the author knows
# which. A blocking gate would force a wrong choice at the worst moment. This
# prints and gets out of the way; `exit 0` is unconditional and deliberate.
#
# WHAT IT DOES NOT DO. It never rewrites anything. The converter that ships with
# the comment-to-docstring skill can misplace a docstring — a declaration-leading
# block can land as the module docstring, and a class-leading block can land in
# `__init__` — so the conversion stays a human decision. This hook only points.
set -uo pipefail

CONVERTER=".claude/skills/comment-to-docstring/scripts/convert_py.py"
[ -f "$CONVERTER" ] || exit 0

mapfile -t FILES < <(git diff --cached --name-only --diff-filter=ACM -- '*.py' 2>/dev/null)
[ ${#FILES[@]} -eq 0 ] && exit 0

FLAGGED=()
for f in "${FILES[@]}"; do
    [ -f "$f" ] || continue
    if ! python3 "$CONVERTER" --check "$f" >/dev/null 2>&1; then
        FLAGGED+=("$f")
    fi
done

if [ ${#FLAGGED[@]} -gt 0 ]; then
    printf '\n\033[33m! grey comments\033[0m — %d staged file(s) have comment blocks where a docstring would go:\n' "${#FLAGGED[@]}"
    for f in "${FLAGGED[@]}"; do printf '    %s\n' "$f"; done
    printf '\n  A comment there is greyed out and invisible to help(), mkdocstrings and the\n'
    printf '  API reference. If it is documentation, make it a docstring; if it is an\n'
    printf '  implementation note, it is already in the right place.\n\n'
    printf '  See:  python3 %s --dry-run <file>\n' "$CONVERTER"
    printf '  (advisory only — this hook never blocks a commit)\n\n'
fi

exit 0
