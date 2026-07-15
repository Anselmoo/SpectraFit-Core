"""Static/structural + injected-logic checks for scripts/purge_github_actions_runs.py.

This script performs real, destructive GitHub API calls (DELETE .../actions/runs/{id}).
None of that can be meaningfully unit-tested without either hitting the real network or
mocking so heavily the test would verify nothing but "the mock was called". These tests
are deliberately limited to what's genuinely checkable without a network call: CLI
argument wiring, --dry-run never calling delete, and pagination/error-handling logic
against a dependency-injected `_request` (not the network). Actual end-to-end behavior
can only be verified by running the manual publish:github job in a real GitLab pipeline
once the GITHUB_TOKEN's Actions:Read-and-write scope is granted.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import purge_github_actions_runs as purge  # noqa: E402  # ty: ignore[unresolved-import]

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "purge_github_actions_runs.py"
)


def _run(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_script_exists() -> None:
    assert _SCRIPT.exists()


def test_requires_token_argument() -> None:
    # CWE-214 hardening: the token is read from the GITHUB_TOKEN env var, not a
    # --token CLI flag (process argv is visible to co-resident processes via ps).
    env_without_token = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
    result = _run("--dry-run", env=env_without_token)
    assert result.returncode != 0
    assert "GITHUB_TOKEN" in result.stderr


def test_dry_run_never_calls_delete() -> None:
    with (
        mock.patch("sys.argv", ["purge_github_actions_runs.py", "--dry-run"]),
        mock.patch.dict(os.environ, {"GITHUB_TOKEN": "x"}),
        mock.patch.object(purge, "list_all_run_ids", return_value=[111, 222]),
        mock.patch.object(purge, "delete_run") as mock_delete,
    ):
        exit_code = purge.main()
    assert exit_code == 0
    mock_delete.assert_not_called()


def test_no_runs_found_is_a_clean_noop() -> None:
    with (
        mock.patch("sys.argv", ["purge_github_actions_runs.py"]),
        mock.patch.dict(os.environ, {"GITHUB_TOKEN": "x"}),
        mock.patch.object(purge, "list_all_run_ids", return_value=[]),
        mock.patch.object(purge, "delete_run") as mock_delete,
    ):
        exit_code = purge.main()
    assert exit_code == 0
    mock_delete.assert_not_called()


def test_pagination_stops_when_page_shorter_than_per_page() -> None:
    """list_all_run_ids must stop paging once a page returns fewer than _PER_PAGE runs."""
    call_log: list[str] = []

    def fake_request(url: str, token: str, method: str = "GET"):
        call_log.append(url)
        page = int(url.rsplit("&page=", 1)[1])
        if page == 1:
            runs = [{"id": i} for i in range(purge._PER_PAGE)]  # full page
        elif page == 2:
            runs = [{"id": 9999}]  # short page -> stop
        else:
            raise AssertionError("should not request a third page")
        return 200, {"workflow_runs": runs}

    with mock.patch.object(purge, "_request", side_effect=fake_request):
        ids = purge.list_all_run_ids("Anselmoo/spectrafit-core", "x")
    assert len(ids) == purge._PER_PAGE + 1
    assert len(call_log) == 2


def test_delete_run_returns_false_and_prints_on_non_204() -> None:
    with mock.patch.object(
        purge, "_request", return_value=(403, {"message": "Forbidden"})
    ):
        ok = purge.delete_run("Anselmoo/spectrafit-core", "x", 42)
    assert ok is False


def test_all_deletions_failing_returns_nonzero() -> None:
    with (
        mock.patch("sys.argv", ["purge_github_actions_runs.py"]),
        mock.patch.dict(os.environ, {"GITHUB_TOKEN": "x"}),
        mock.patch.object(purge, "list_all_run_ids", return_value=[1, 2]),
        mock.patch.object(purge, "delete_run", return_value=False),
    ):
        exit_code = purge.main()
    assert exit_code == 1
