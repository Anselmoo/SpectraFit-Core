#!/usr/bin/env bash
# Stop-hook gate for the DECISIONS.md ADR reminder.
#
# Problem it solves: the previous Stop hook was an unconditional `prompt` that
# fired on EVERY turn — including idle turns with a clean tree while awaiting
# user input — producing a feedback loop that blocked development.
#
# if/else matching: only remind (exit 2, which feeds the message back to the
# model) when BOTH hold:
#   1. the working tree has uncommitted changes to decision-worthy areas
#      (solver/schemas/bindings/oracles/web/CI), AND
#   2. DECISIONS.md is NOT itself among the changed files.
# In every other case — clean tree, doc/skill-only edits, or DECISIONS.md
# already updated — exit 0 silently (no nag).
set -uo pipefail

root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$root" || exit 0

changed="$(git status --porcelain 2>/dev/null | sed 's/^...//')"
[ -z "$changed" ] && exit 0                      # clean tree → nothing to record

# DECISIONS.md already touched this session → assume the decision is recorded.
printf '%s\n' "$changed" | grep -qx 'DECISIONS.md' && exit 0

# Decision-worthy areas: behavioural/architectural surfaces. Doc/skill/test-only
# edits do NOT match, so they never trigger the reminder.
if printf '%s\n' "$changed" | grep -qE '^(crates/|python/spectrafit_core/|python/oracles/|web/|\.github/workflows/)'; then
  echo "DECISIONS.md not updated, but the working tree has uncommitted changes to a \
behavioural/architectural surface (crates / spectrafit_core / oracles / web / CI). \
If this change embodies an architectural or behavioural decision, append an ADR to \
DECISIONS.md — top entry '## [YYYY-MM-DD] <Title>' with **Context**/**Decision**/\
**Rationale**/**Trade-offs**, naming the files/symbols. Skip for trivial work \
(typos, comments/docstrings, dep bumps, pure refactors, read-only investigation)." >&2
  exit 2
fi
exit 0
