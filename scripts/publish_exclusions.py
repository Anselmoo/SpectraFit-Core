#!/usr/bin/env python3
"""Single source of truth for paths excluded from the GitHub sneak-preview publish.

Consulted from two places, which is exactly why this exists as its own module:

1. ``scripts/publish_remove_excluded.py`` — removes these paths from the real
   ``main`` checkout before ``rrt git publish-snapshot`` ever creates its
   orphan branch (working around a repo-release-tools 1.11.2 bug in its own
   ``--exclude`` handling; see ``.gitlab/70-publish.yml``).
2. ``scripts/fast_lane_gate.py`` — the fast-lane diff-gate excludes these same
   paths before asserting "is everything else under .github/**?", since they
   are expected to always differ between the GitLab and GitHub remotes and
   would otherwise always fail the gate.

Keeping ONE list here means the patterns cannot drift out of sync between the
two call sites. Note: ``pyproject.toml``'s
``[tool.rrt.publish_targets.github].exclude`` TOML array duplicates this list
for documentation purposes only — it is inert (rrt's own ``--exclude`` flag is
deliberately never invoked; see the bug note in ``.gitlab/70-publish.yml``).
This module, not the TOML array, is the actual source of truth at runtime.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable

EXCLUDE_PATTERNS: tuple[str, ...] = (
    "docs/superpowers/plans/*",
    "docs/superpowers/specs/*",
    "docs/superpowers/ledgers/*",
    ".claude/audit/*.jsonl",
    "DECISIONS.md",
)


def is_excluded(path: str) -> bool:
    """Return True if ``path`` matches any of the shared exclude patterns."""
    return any(fnmatch.fnmatch(path, pattern) for pattern in EXCLUDE_PATTERNS)


def filter_excluded(paths: Iterable[str]) -> list[str]:
    """Return ``paths`` with every excluded entry removed, order preserved."""
    return [path for path in paths if not is_excluded(path)]
