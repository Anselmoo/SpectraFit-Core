"""Tests for scripts/publish_exclusions.py — the single source of truth for
paths excluded from every GitHub sneak-preview publish (both the exclusion-
removal step and the fast-lane diff-gate consult this same list)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from publish_exclusions import (  # ty: ignore[unresolved-import]
    EXCLUDE_PATTERNS,
    filter_excluded,
    is_excluded,
)


def test_exclude_patterns_match_known_paths() -> None:
    known_excluded = [
        "docs/superpowers/plans/2026-07-01-something.md",
        "docs/superpowers/specs/2026-07-11-github-publish-fast-lane-design.md",
        "docs/superpowers/ledgers/2026-07-01-ledger.md",
        ".claude/audit/2026-07-01.jsonl",
        "DECISIONS.md",
        ".claude/docs/migration-github-to-claude.md",
        "docs/audit-2026-07-02-three-language-audit.md",
        "docs/cycle11-backend-card-before.png",
    ]
    for path in known_excluded:
        assert is_excluded(path), f"expected {path!r} to be excluded"


def test_non_excluded_paths_are_not_matched() -> None:
    not_excluded = [
        ".github/workflows/ci.yml",
        "python/spectrafit_core/fit.py",
        "scripts/publish_exclusions.py",
        "docs/superpowers/README.md",
        ".claude/audit.jsonl",
    ]
    for path in not_excluded:
        assert not is_excluded(path), f"did not expect {path!r} to be excluded"


def test_filter_excluded_removes_only_matching_paths() -> None:
    paths = [
        ".github/workflows/ci.yml",
        "DECISIONS.md",
        "docs/superpowers/plans/x.md",
        "pyproject.toml",
    ]
    result = filter_excluded(paths)
    assert result == [".github/workflows/ci.yml", "pyproject.toml"]


def test_exclude_patterns_is_a_tuple_of_eleven_known_globs() -> None:
    """Pin the exclusion set exactly — an accidental addition silently changes
    what reaches the public GitHub mirror.

    This list is an ALLOWLIST OF PATHS TO STRIP: anything absent from it ships
    publicly. That asymmetry is why the set is pinned rather than merely
    smoke-tested — a wrong *addition* is cosmetic, a wrong *omission* publishes
    something private.

    History, deliberately kept: was eight until `analysis/*` (080112a), then
    eleven on 2026-08-02 when superpowers artifacts moved out of the published
    Zensical tree into top-level `.superpowers/`. `superpowers/*` (undotted) is
    listed alongside it — unused today, but the bare form would otherwise be a
    silent publish the moment anyone created it.

    The `docs/superpowers/*` entries are retained even though that directory no
    longer exists: they cost nothing and keep the guard in place if a future
    skill default recreates it. `.claude/skills/semantic-debugging` was
    retargeted to `.superpowers/ledgers/` in the same change, along with
    `.claude/hooks/guard-ledger-freshness.sh`'s `LEDGER_DIR` — if those two ever
    disagree, the reaper scans an empty directory and reports success forever.
    """
    assert EXCLUDE_PATTERNS == (
        "docs/superpowers/plans/*",
        "docs/superpowers/specs/*",
        "docs/superpowers/ledgers/*",
        ".claude/audit/*.jsonl",
        "DECISIONS.md",
        ".claude/docs/*",
        "docs/audit-2026-07-02-*.md",
        "docs/cycle11-backend-card-*.png",
        "analysis/*",
        ".superpowers/*",
        "superpowers/*",
    )
