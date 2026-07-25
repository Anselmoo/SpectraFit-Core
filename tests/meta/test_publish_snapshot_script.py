"""Static/structural checks for scripts/publish_snapshot.sh.

This script performs real network calls (GitHub API smoke test) and real,
destructive git-remote operations (rrt git publish-snapshot). None of that
can be meaningfully unit-tested without either hitting the real network or
mocking so heavily the test would verify nothing but "the mock was called".

These tests are deliberately limited to what's genuinely checkable without a
network call. Actual end-to-end behavior can only be verified by triggering
the manual publish:github job in a real GitLab pipeline — see the design
spec's testing plan.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "publish_snapshot.sh"


def test_script_exists_and_is_executable() -> None:
    assert _SCRIPT.exists(), f"expected {_SCRIPT} to exist"
    mode = _SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, f"{_SCRIPT} must be executable (chmod +x)"


def test_script_is_valid_bash_syntax() -> None:
    bash = shutil.which("bash")
    assert bash is not None, "bash must be on PATH to syntax-check the script"
    result = subprocess.run(
        [bash, "-n", str(_SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_script_smoke_tests_github_token_before_any_destructive_action() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    smoke_idx = text.find("api.github.com/repos/Anselmoo/spectrafit-core")
    remote_idx = text.find("git remote add github")
    assert smoke_idx != -1, "expected a GITHUB_TOKEN smoke-test curl call"
    assert remote_idx != -1, "expected a `git remote add github` line"
    assert smoke_idx < remote_idx, (
        "the GITHUB_TOKEN smoke test must run BEFORE `git remote add github` "
        "so a bad token aborts before any destructive git action"
    )


def test_script_pins_rrt_to_exact_version() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "repo-release-tools==1.11.2" in text, (
        "rrt must be pinned via --from 'repo-release-tools==1.11.2', not @latest"
    )


def test_script_calls_the_exclusion_removal_script() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "publish_remove_excluded.py" in text


def test_script_calls_the_actions_purge_script() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "purge_github_actions_runs.py" in text


def test_purge_call_does_not_abort_the_script_on_failure() -> None:
    """The purge runs after set -euo pipefail; a purge failure (expected pre-scope-
    grant) must not abort the script after the publish itself already succeeded."""
    text = _SCRIPT.read_text(encoding="utf-8")
    purge_idx = text.find("purge_github_actions_runs.py")
    assert purge_idx != -1
    # The purge invocation line (or its continuation) must be followed by `|| echo`
    # so a non-zero exit doesn't propagate under `set -e`.
    snippet = text[purge_idx : purge_idx + 200]
    assert "|| echo" in snippet


def test_script_uses_yes_i_know_flag() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "--yes-i-know-this-overwrites-remote-history" in text


def test_remote_add_calls_are_idempotent() -> None:
    """Both remote-add lines must tolerate the remote already existing —
    publish:github:fast adds the `github` remote itself before calling this
    shared script."""
    text = _SCRIPT.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().startswith("git remote add"):
            assert "|| true" in line, f"expected idempotent remote-add, got: {line}"
