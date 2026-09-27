"""Tests for scripts/guard_public_push.py.

Runs the guard as a subprocess against a scratch git repo, in both of the forms
it is invoked in: as a plain git pre-push hook (argv + stdin ref lines) and
under pre-commit (``PRE_COMMIT_*`` environment variables).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "guard_public_push.py"
GITHUB_URL = "https://github.com/example/mirror.git"
GITHUB_SSH_URL = "git@github.com:example/mirror.git"
GITLAB_URL = "https://gitlab.mpcdf.mpg.de/example/primary.git"
ZERO = "0" * 40


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _commit(repo: Path, files: dict[str, str]) -> str:
    for rel, text in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    return tmp_path


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("PRE_COMMIT_")}


def _as_git_hook(repo: Path, url: str, sha: str) -> subprocess.CompletedProcess[str]:
    stdin = f"refs/heads/main {sha} refs/heads/main {ZERO}\n"
    return subprocess.run(
        [sys.executable, str(SCRIPT), "mirror", url],
        cwd=repo,
        input=stdin,
        capture_output=True,
        text=True,
        env=_clean_env(),
        check=False,
    )


def _as_pre_commit(repo: Path, url: str, **refs: str) -> subprocess.CompletedProcess[str]:
    env = {**_clean_env(), "PRE_COMMIT_REMOTE_URL": url, "PRE_COMMIT_REMOTE_NAME": "mirror"}
    env.update(refs)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


PUBLIC_TREE = {"README.md": "hi\n", "scripts/tool.py": "print(1)\n"}
PRIVATE_TREE = {**PUBLIC_TREE, "analysis/x.md": "private\n"}


def test_filtered_tree_to_github_is_allowed(repo: Path) -> None:
    sha = _commit(repo, PUBLIC_TREE)
    result = _as_git_hook(repo, GITHUB_URL, sha)
    assert result.returncode == 0, result.stderr


def test_private_path_to_github_is_blocked(repo: Path) -> None:
    sha = _commit(repo, PRIVATE_TREE)
    result = _as_git_hook(repo, GITHUB_URL, sha)
    assert result.returncode == 1
    assert "analysis/x.md" in result.stderr
    assert "publish:github" in result.stderr


def test_private_path_to_github_ssh_url_is_blocked(repo: Path) -> None:
    sha = _commit(repo, PRIVATE_TREE)
    assert _as_git_hook(repo, GITHUB_SSH_URL, sha).returncode == 1


def test_private_path_in_an_ancestor_is_still_blocked(repo: Path) -> None:
    _commit(repo, PRIVATE_TREE)
    sha = _commit(repo, {"README.md": "harmless follow-up\n"})
    assert _as_git_hook(repo, GITHUB_URL, sha).returncode == 1


def test_private_path_deleted_before_push_is_still_blocked(repo: Path) -> None:
    """The tip's tree is clean, but the history still carries the private blob."""
    _commit(repo, PRIVATE_TREE)
    _git(repo, "rm", "-q", "-r", "analysis")
    _git(repo, "commit", "-q", "-m", "drop it again")
    sha = _git(repo, "rev-parse", "HEAD")
    result = _as_git_hook(repo, GITHUB_URL, sha)
    assert result.returncode == 1
    assert "analysis/x.md" in result.stderr


def test_history_already_on_the_remote_is_not_rescanned(repo: Path) -> None:
    """Only commits the remote lacks are scanned; the tip tree always is."""
    old = _commit(repo, PRIVATE_TREE)
    _git(repo, "update-ref", "refs/remotes/mirror/main", old)
    _git(repo, "rm", "-q", "-r", "analysis")
    _git(repo, "commit", "-q", "-m", "drop it again")
    sha = _git(repo, "rev-parse", "HEAD")
    result = _as_git_hook(repo, GITHUB_URL, sha)
    assert result.returncode == 0, result.stderr


def test_push_to_gitlab_is_always_allowed(repo: Path) -> None:
    sha = _commit(repo, PRIVATE_TREE)
    result = _as_git_hook(repo, GITLAB_URL, sha)
    assert result.returncode == 0, result.stderr


def test_branch_delete_to_github_is_allowed(repo: Path) -> None:
    _commit(repo, PRIVATE_TREE)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "mirror", GITHUB_URL],
        cwd=repo,
        input=f"(delete) {ZERO} refs/heads/old {'1' * 40}\n",
        capture_output=True,
        text=True,
        env=_clean_env(),
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_pre_commit_form_checks_to_ref(repo: Path) -> None:
    sha = _commit(repo, PRIVATE_TREE)
    assert _as_pre_commit(repo, GITHUB_URL, PRE_COMMIT_TO_REF=sha).returncode == 1
    assert _as_pre_commit(repo, GITLAB_URL, PRE_COMMIT_TO_REF=sha).returncode == 0


def test_pre_commit_first_push_without_to_ref_is_checked(repo: Path) -> None:
    """pre-commit sets no TO_REF when pushing into an empty remote."""
    _commit(repo, PRIVATE_TREE)
    result = _as_pre_commit(repo, GITHUB_URL, PRE_COMMIT_LOCAL_BRANCH="refs/heads/main")
    assert result.returncode == 1


def test_pre_commit_form_filtered_tree_is_allowed(repo: Path) -> None:
    sha = _commit(repo, PUBLIC_TREE)
    result = _as_pre_commit(repo, GITHUB_URL, PRE_COMMIT_TO_REF=sha)
    assert result.returncode == 0, result.stderr
