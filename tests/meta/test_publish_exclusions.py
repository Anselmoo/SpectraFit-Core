"""Tests for scripts/publish_exclusions.py — the include list that decides
what reaches the public GitHub mirror."""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from publish_exclusions import (  # ty: ignore[unresolved-import]
    EXCLUDE_PATTERNS,
    PRIVATE_ROOTS,
    PUBLISH_INCLUDE,
    filter_excluded,
    is_excluded,
    is_published,
)


def test_private_working_trees_are_excluded() -> None:
    private = [
        "analysis/crates/PREFLIGHT.md",
        ".superpowers/specs/2026-09-22-something-design.md",
        "superpowers/plans/x.md",
        "docs/superpowers/plans/2026-07-01-something.md",
        "vibe-sessions/.gitkeep",
        "test-results/.last-run.json",
        ".spectrafit_reports/perf_baseline.json",
        ".vscode/settings.json",
        ".serena/project.yml",
        ".claude/settings.local.json",
        ".claude/self-assess.local.md",
        ".claude/scheduled_tasks.lock",
        ".claude/audit/2026-07-01.jsonl",
        ".claude/docs/notes.md",
        ".claude/workflows/github-release.js",
        "a-new-top-level-dir/file.md",
        "NEW_ROOT_FILE.md",
    ]
    for path in private:
        assert is_excluded(path), f"expected {path!r} to stay private"


def test_public_paths_are_published() -> None:
    public = [
        "python/spectrafit_core/fit.py",
        "crates/spectrafit-core/src/lib.rs",
        "web/src/main.tsx",
        "docs/index.md",
        "tests/meta/test_publish_exclusions.py",
        "reproducibility/figures/fig_architecture.py",
        "scripts/publish_exclusions.py",
        ".github/workflows/ci.yml",
        ".gitlab/70-publish.yml",
        ".claude/settings.json",
        ".claude/hooks/run-hook.sh",
        "CLAUDE.md",
        "README.md",
        "pyproject.toml",
    ]
    for path in public:
        assert is_published(path), f"expected {path!r} to be published"


def test_filter_excluded_keeps_only_published_paths() -> None:
    paths = [
        ".github/workflows/ci.yml",
        "analysis/crates/PREFLIGHT.md",
        "docs/superpowers/plans/x.md",
        "pyproject.toml",
        "unknown/file.txt",
    ]
    assert filter_excluded(paths) == [".github/workflows/ci.yml", "pyproject.toml"]


def test_patterns_are_tuples_without_duplicates() -> None:
    for patterns in (PUBLISH_INCLUDE, EXCLUDE_PATTERNS):
        assert isinstance(patterns, tuple)
        assert len(patterns) == len(set(patterns))


def test_every_tracked_top_level_entry_is_classified_on_purpose() -> None:
    """A tracked top-level entry that is neither published nor on the known
    private list is a new directory nobody has decided about yet.

    It stays private by construction; this test makes the decision visible so
    it is taken deliberately rather than by omission.
    """
    known_private = set(PRIVATE_ROOTS)
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    undecided = sorted(
        {
            path.split("/", 1)[0]
            for path in tracked
            if not any(fnmatch.fnmatch(path, pattern) for pattern in PUBLISH_INCLUDE)
            and path.split("/", 1)[0] not in known_private
        },
    )
    assert undecided == [], (
        "Tracked paths outside the publish scope that are not in PRIVATE_ROOTS "
        f"list: {undecided}. Add them to PUBLISH_INCLUDE or PRIVATE_ROOTS."
    )
