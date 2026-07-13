"""Tests for scripts/publish_remove_excluded.py.

Runs the script as a subprocess against a scratch git repo, mirroring the
tests/meta/test_self_heal_automation.py convention."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_remove_excluded(repo: Path) -> subprocess.CompletedProcess[str]:
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "publish_remove_excluded.py"
    )
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def _init_repo(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)


def test_removes_excluded_paths_and_leaves_others(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    (tmp_path / "docs" / "superpowers" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "superpowers" / "plans" / "x.md").write_text("plan")
    (tmp_path / ".claude" / "audit").mkdir(parents=True)
    (tmp_path / ".claude" / "audit" / "run.jsonl").write_text("{}")
    (tmp_path / "DECISIONS.md").write_text("decisions")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")

    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, check=True)

    result = _run_remove_excluded(tmp_path)

    assert result.returncode == 0, result.stderr
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert "docs/superpowers/plans/x.md" not in tracked
    assert ".claude/audit/run.jsonl" not in tracked
    assert "DECISIONS.md" not in tracked
    assert ".github/workflows/ci.yml" in tracked
    assert not (tmp_path / "DECISIONS.md").exists()
    assert (tmp_path / ".github" / "workflows" / "ci.yml").exists()


def test_no_excluded_paths_present_is_a_no_op(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, check=True)

    result = _run_remove_excluded(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "No excluded paths matched" in result.stdout
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert tracked == [".github/workflows/ci.yml"]
