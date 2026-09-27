#!/usr/bin/env python3
"""Single source of truth for what reaches the public GitHub mirror.

The publish scope is an **include list**: a tracked path is published only if
it matches one of :data:`PUBLISH_INCLUDE`, and even then not if it matches one
of :data:`EXCLUDE_PATTERNS`. Anything else stays on the primary (GitLab)
remote. A new top-level directory is therefore private until someone adds it
here on purpose; it cannot reach the mirror by being forgotten.

Consulted from four places, which is why it is its own module:

1. ``scripts/publish_sync.py`` — builds the filtered tree for the GitLab ->
   GitHub sync commit.
2. ``scripts/publish_remove_excluded.py`` — removes non-published paths from a
   checkout before the manual orphan-snapshot reset (``publish:github:reset``).
3. ``scripts/fast_lane_gate.py`` — drops non-published paths before asserting
   that a fast-lane change touches only ``.github/**``.
4. ``scripts/guard_public_push.py`` — pre-push hook refusing any push to a
   github.com remote whose tree contains a non-published path, so no branch
   can reach the mirror around the sync.

``pyproject.toml``'s ``[tool.rrt.publish_targets.github]`` table is
informational only; rrt's own ``--exclude`` flag is never invoked, so this
module, not the TOML table, decides what is published.

``fnmatch``'s ``*`` spans ``/``, so a single ``"<dir>/*"`` pattern covers every
nested path under that directory.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable

#: Tracked paths that may be published. Directories use ``"<dir>/*"``; single
#: files are listed by exact name.
PUBLISH_INCLUDE: tuple[str, ...] = (
    # Source, tests, documentation and reproducible evidence.
    "crates/*",
    "python/*",
    "web/*",
    "docs/*",
    "overrides/*",
    "tests/*",
    "reproducibility/*",
    "benchmark/*",
    "scripts/*",
    # CI and development tooling (published for transparency and FAIR reuse).
    ".github/*",
    ".gitlab/*",
    ".gitlab-ci.yml",
    ".claude/*",
    "CLAUDE.md",
    ".mcp.json",
    ".pre-commit-config.yaml",
    # Project metadata and build manifests.
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "CITATION.cff",
    "codemeta.json",
    ".zenodo.json",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "LIMITATIONS.md",
    "ARCHITECTURE.md",
    "CODEOWNERS",
    "Cargo.toml",
    "Cargo.lock",
    "pyproject.toml",
    "uv.lock",
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "zensical.toml",
    ".gitignore",
    ".python-version",
)

#: Paths inside an included tree that must still stay private: per-machine
#: tool state and working artifacts that skills write under ``docs/`` by
#: default.
EXCLUDE_PATTERNS: tuple[str, ...] = (
    ".claude/*.local.md",
    ".claude/*.local.json",
    ".claude/scheduled_tasks.lock",
    ".claude/audit/*.jsonl",
    ".claude/docs/*",
    ".claude/workflows/*",
    "docs/superpowers/*",
)


#: Top-level directories that are tracked on the primary remote but are never
#: published (working artifacts, local tool state). Everything outside
#: :data:`PUBLISH_INCLUDE` is private anyway; this list names the known cases so
#: guards can tell "a private repo path" from "an arbitrary string".
PRIVATE_ROOTS: tuple[str, ...] = (
    "analysis",
    ".superpowers",
    "superpowers",
    "vibe-sessions",
    "test-results",
    ".spectrafit_reports",
    ".vscode",
)


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def is_published(path: str) -> bool:
    """Return True if ``path`` is inside the public publish scope."""
    return _matches(path, PUBLISH_INCLUDE) and not _matches(path, EXCLUDE_PATTERNS)


def is_excluded(path: str) -> bool:
    """Return True if ``path`` must not reach the public mirror."""
    return not is_published(path)


def filter_excluded(paths: Iterable[str]) -> list[str]:
    """Return ``paths`` with every non-published entry removed, order preserved."""
    return [path for path in paths if is_published(path)]
