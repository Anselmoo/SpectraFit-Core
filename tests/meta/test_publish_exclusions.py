"""Tests for scripts/publish_exclusions.py — the single source of truth for
paths excluded from every GitHub sneak-preview publish (both the exclusion-
removal step and the fast-lane diff-gate consult this same list)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from publish_exclusions import EXCLUDE_PATTERNS, filter_excluded, is_excluded  # noqa: E402  # ty: ignore[unresolved-import]


def test_exclude_patterns_match_known_paths() -> None:
    known_excluded = [
        "docs/superpowers/plans/2026-07-01-something.md",
        "docs/superpowers/specs/2026-07-11-github-publish-fast-lane-design.md",
        "docs/superpowers/ledgers/2026-07-01-ledger.md",
        ".claude/audit/2026-07-01.jsonl",
        "DECISIONS.md",
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


def test_exclude_patterns_is_a_tuple_of_five_known_globs() -> None:
    assert EXCLUDE_PATTERNS == (
        "docs/superpowers/plans/*",
        "docs/superpowers/specs/*",
        "docs/superpowers/ledgers/*",
        ".claude/audit/*.jsonl",
        "DECISIONS.md",
    )
