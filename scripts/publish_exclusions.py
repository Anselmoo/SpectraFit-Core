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
    # Internal Claude/hook-tooling docs relocated out of docs/ (see
    # analysis/andon/ledger-docs-publish/gaps/gap-0-relocate-internal-docs.md) —
    # not spectrafit-core's public API documentation, so excluded even at
    # their new .claude/docs/ path since .claude/ is otherwise published
    # wholesale today.
    ".claude/docs/*",
    # Process ephemera from a specific audit cycle — never actually excluded
    # despite being assumed excluded by an earlier docs-drift scope note.
    "docs/audit-2026-07-02-*.md",
    "docs/cycle11-backend-card-*.png",
    # codebase-consistency / andon working artifacts (PREFLIGHT, scan findings,
    # module×dimension matrix + its HTML viewer, alignment briefs, ledgers).
    # Internal process record of how the codebase got aligned — same class as
    # DECISIONS.md, not public API documentation. Note `fnmatch`'s `*` spans
    # `/`, so this single pattern covers nested paths like
    # `analysis/crates/PREFLIGHT.md` as well.
    "analysis/*",
    # Superpowers working artifacts (brainstorming specs, writing-plans plans,
    # ledgers). Same class as the `docs/superpowers/*` patterns above and
    # `analysis/*`: process record, not public documentation. Tracked on GitLab
    # so design history survives; stripped from the GitHub mirror.
    #
    # NAMING CONVENTION — dot-prefix what WE control, leave tool-owned paths as
    # the tool names them:
    #   `.superpowers/`  canonical, ours. Holds `specs/`, `plans/`, `ledgers/`,
    #                    plus a `.gitkeep` so the directory survives when empty.
    #   `analysis/`      NOT dot-prefixed, and deliberately so: the
    #                    codebase-consistency plugin writes `analysis/<area>/…`
    #                    as a hardcoded path. Renaming it would break every
    #                    future `/consistency-*` invocation. It is also cited
    #                    across DECISIONS.md, tracked docs, and commit messages.
    #   `.claude/docs/`  excluded above, same reasoning.
    #
    # Both `.superpowers/*` and `superpowers/*` are listed. The bare form is not
    # in use today, but this list is an ALLOWLIST OF PATHS TO STRIP — anything
    # absent from it ships to the public GitHub mirror. Carrying the second
    # pattern costs nothing and closes the failure mode where someone creates
    # the non-dotted variant and it silently publishes.
    ".superpowers/*",
    "superpowers/*",
)


def is_excluded(path: str) -> bool:
    """Return True if ``path`` matches any of the shared exclude patterns."""
    return any(fnmatch.fnmatch(path, pattern) for pattern in EXCLUDE_PATTERNS)


def filter_excluded(paths: Iterable[str]) -> list[str]:
    """Return ``paths`` with every excluded entry removed, order preserved."""
    return [path for path in paths if not is_excluded(path)]
