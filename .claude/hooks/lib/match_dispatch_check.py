#!/usr/bin/env python3
"""Shared match/case dispatch-chain detector (GOV-07).

Single source of truth for the "if/elif <var>== ... chain instead of match/case"
check CLAUDE.md's Code Conventions names for ``python/oracles/**``,
``python/extras/**`` and ``tests/**``. Two entry points call this module so the
detection regex/logic lives in exactly one place:

  * ``.claude/hooks/enforce-match-dispatch.sh`` — the Claude Code PreToolUse
    hook (JSON payload on stdin, blocks an Edit/Write with exit 2).
  * ``.claude/hooks/warn-match-dispatch.sh`` — the git pre-commit entry point
    (scans already-staged file content, exit 0, never blocks — see that
    script's header for why it starts warn-only).

Before this module existed the check lived only inline inside
enforce-match-dispatch.sh's embedded Python heredoc, which is easy to escape:
CLAUDE.md's own documented "write through Bash heredoc" workaround for the
self-assess write-gate silently bypasses any Edit/Write PreToolUse hook,
including this one. A pre-commit gate over staged files closes that gap
without a second, drifting copy of the regex.
"""

from __future__ import annotations

import re
from pathlib import Path

# Scope: CLAUDE.md Code Conventions — "2+ if/elif branches on the same
# variable in python/oracles/** or tests/** will fail at edit time". The
# PreToolUse hook has always additionally covered python/extras/ (see its
# existing HookContract in tests/meta/test_hook_enforcement.py); kept as-is
# rather than narrowed, since narrowing would be a behavior change, not an
# extraction.
TARGET_PREFIXES: tuple[str, ...] = (
    "python/extras/",
    "python/oracles/",
    "tests/",
)

# Flag if/elif == dispatch chains on a discriminator: two or more equality
# branches comparing the SAME identifier against a value. A lone `if x == y:`
# is fine; a chain (`if x == A: ... elif x == B: ...`) should be `match x:` with
# `case A:` per CLAUDE.md Code Conventions. Anchoring on `^\s*(if|elif) IDENT ==`
# keeps comments and strings (not Python branch lines) out of the match.
_BRANCH_RE = re.compile(r"^[ \t]*(?:if|elif)[ \t]+([A-Za-z_][\w.]*)[ \t]*==[ \t]*[^=]")


def is_target_path(path_value: str) -> tuple[bool, str]:
    """Return (in_scope, normalized_posix_path) for a candidate file path."""
    path = Path(path_value)
    normalized = path.as_posix()
    in_scope = normalized.startswith(TARGET_PREFIXES) and path.suffix == ".py"
    return in_scope, normalized


def find_offenders(text: str) -> dict[str, list[int]]:
    """Return {variable: [1-based line numbers]} for every discriminator
    dispatched on by 2+ if/elif==... branches. Empty dict = clean."""
    where: dict[str, list[int]] = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        m = _BRANCH_RE.match(line)
        if m:
            where.setdefault(m.group(1), []).append(lineno)
    return {var: locs for var, locs in where.items() if len(locs) >= 2}


def format_reason(normalized_path: str, offenders: dict[str, list[int]]) -> str:
    """Render the same violation message the PreToolUse hook has always
    printed, picking the worst-offending variable when several dispatch on
    different discriminators in one file."""
    var, locs = max(offenders.items(), key=lambda kv: len(kv[1]))
    n = len(locs)
    locs_str = ", ".join(f"L{ln}" for ln in locs[:4])
    return (
        f"match/case violation in {normalized_path}: {n} if/elif {var}==... dispatch "
        f"branches ({locs_str}). Use 'match {var}:' with 'case ...:' for discriminator "
        f"dispatch (CLAUDE.md Code Conventions). A single 'if x == y:' is fine; "
        f"chains on the same variable are not."
    )


def check_text(path_value: str, text: str) -> str | None:
    """Full check for one (path, proposed-or-staged content) pair.

    Returns the violation message, or None if the path is out of scope or
    clean.
    """
    in_scope, normalized = is_target_path(path_value)
    if not in_scope:
        return None
    offenders = find_offenders(text)
    if not offenders:
        return None
    return format_reason(normalized, offenders)
