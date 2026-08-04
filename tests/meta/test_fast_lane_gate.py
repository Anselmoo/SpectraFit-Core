"""Tests for scripts/fast_lane_gate.py — the fast-lane publish diff-gate.

Covers: all-`.github/`-diff passes; a non-`.github/` path fails with a
message pointing at publish:github; a broken YAML file fails with a clear
message; the known exclude-list paths are correctly ignored.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_gate(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[2] / "scripts" / "fast_lane_gate.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def _init_repo_with_commit(repo: Path, files: dict[str, str]) -> str:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    for rel_path, content in files.items():
        path = repo / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _commit_changes(
    repo: Path, files: dict[str, str], removed: list[str] | None = None
) -> None:
    for rel_path, content in files.items():
        path = repo / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for rel_path in removed or []:
        (repo / rel_path).unlink()
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "head"], cwd=repo, check=True)


def test_all_github_workflow_diff_passes(tmp_path: Path) -> None:
    base_sha = _init_repo_with_commit(
        tmp_path, {".github/workflows/ci.yml": "name: ci\non: push\n"}
    )
    _commit_changes(
        tmp_path, {".github/workflows/ci.yml": "name: ci\non: [push, pull_request]\n"}
    )
    result = _run_gate(tmp_path, base_sha, "HEAD")
    assert result.returncode == 0, result.stdout + result.stderr


def test_non_github_path_fails_with_pointer_to_full_pipeline(tmp_path: Path) -> None:
    base_sha = _init_repo_with_commit(tmp_path, {"README.md": "hello\n"})
    _commit_changes(
        tmp_path,
        {
            ".github/workflows/ci.yml": "name: ci\n",
            "python/spectrafit_core/fit.py": "# changed\n",
        },
    )
    result = _run_gate(tmp_path, base_sha, "HEAD")
    assert result.returncode == 1
    assert "python/spectrafit_core/fit.py" in result.stdout + result.stderr
    assert "publish:github" in result.stdout + result.stderr


def test_broken_yaml_file_fails_with_clear_message(tmp_path: Path) -> None:
    base_sha = _init_repo_with_commit(
        tmp_path, {".github/workflows/ci.yml": "name: ci\n"}
    )
    _commit_changes(
        tmp_path,
        {".github/workflows/ci.yml": "name: ci\n  bad indent: [unclosed\n"},
    )
    result = _run_gate(tmp_path, base_sha, "HEAD")
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert ".github/workflows/ci.yml" in combined
    assert "yaml" in combined.lower() or "parse" in combined.lower()


def test_known_excluded_paths_are_ignored(tmp_path: Path) -> None:
    base_sha = _init_repo_with_commit(tmp_path, {"DECISIONS.md": "old\n"})
    _commit_changes(
        tmp_path,
        {
            "DECISIONS.md": "new decision\n",
            "docs/superpowers/plans/2026-07-11-x.md": "plan\n",
            "docs/superpowers/specs/2026-07-11-y.md": "spec\n",
            "docs/superpowers/ledgers/2026-07-11-z.md": "ledger\n",
            ".claude/audit/run.jsonl": "{}\n",
            ".github/workflows/ci.yml": "name: ci\n",
        },
    )
    result = _run_gate(tmp_path, base_sha, "HEAD")
    assert result.returncode == 0, result.stdout + result.stderr


def test_head_ref_defaults_to_head(tmp_path: Path) -> None:
    base_sha = _init_repo_with_commit(
        tmp_path, {".github/workflows/ci.yml": "name: ci\n"}
    )
    _commit_changes(tmp_path, {".github/workflows/ci.yml": "name: ci\non: push\n"})
    result = _run_gate(tmp_path, base_sha)
    assert result.returncode == 0, result.stdout + result.stderr


def test_bad_base_ref_fails_with_clear_message(tmp_path: Path) -> None:
    _init_repo_with_commit(tmp_path, {".github/workflows/ci.yml": "name: ci\n"})
    _commit_changes(tmp_path, {".github/workflows/ci.yml": "name: ci\non: push\n"})
    result = _run_gate(tmp_path, "nonexistent_ref", "HEAD")
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    # Should print a clear message, not a Python traceback.
    assert "fast_lane_gate: FAILED" in combined
    assert "Could not diff" in combined or "nonexistent_ref" in combined
    assert "publish:github" in combined
    assert "Traceback" not in combined
    assert "CalledProcessError" not in combined
