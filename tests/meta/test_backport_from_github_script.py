"""Structural + logic checks for scripts/backport_from_github.py.

fetch_github_remote() does a real network `git fetch`; commits_only_on_github() is pure
git-log parsing and IS meaningfully unit-testable against a real local git history (using
a throwaway local branch to stand in for "github/main" — no network needed for this part).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import backport_from_github as backport  # noqa: E402  # ty: ignore[unresolved-import]

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backport_from_github.py"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )


def test_script_exists() -> None:
    assert _SCRIPT.exists()


def test_commits_only_on_github_returns_empty_for_identical_refs() -> None:
    assert backport.commits_only_on_github("HEAD", "HEAD") == []


def test_commits_only_on_github_parses_sha_and_subject(tmp_path: Path) -> None:
    # Build a tiny throwaway repo: base commit, a "github-main" branch standing in
    # for the mirror, then one direct-edit commit ahead of local main.
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "f.txt").write_text("one\n")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", "base commit")
    _git(repo, "checkout", "-q", "-b", "github-main")
    (repo / "f.txt").write_text("two\n")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", "direct github edit")

    import os

    old_cwd = os.getcwd()
    os.chdir(repo)
    try:
        commits = backport.commits_only_on_github("github-main", "main")
    finally:
        os.chdir(old_cwd)

    assert len(commits) == 1
    assert commits[0][1] == "direct github edit"
    assert len(commits[0][0]) == 40  # full SHA


def test_main_reports_no_commits_when_up_to_date(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "f.txt").write_text("one\n")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", "base commit")

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--remote-name",
            "self",
            "--remote-url",
            str(repo),
            "--branch",
            "main",
            "--local-ref",
            "main",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "no commits" in result.stdout.lower()
