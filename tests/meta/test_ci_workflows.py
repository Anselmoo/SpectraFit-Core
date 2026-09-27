"""Structure checks for the GitHub CI and Claude review workflows.

Two failures these pin, both found on the public mirror:

* the CI tested Linux/CPython 3.13 only, while the classifiers promise macOS,
  Windows and ``requires-python >=3.13`` (so 3.14) -- ``test-matrix`` covers
  the rest;
* the Claude review workflow ran, billed and posted nothing, because in
  ``prompt:`` mode the action denies ``gh pr comment`` unless ``claude_args``
  allows it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((_WORKFLOWS / name).read_text())


def test_test_matrix_covers_every_platform_and_python() -> None:
    include = _load("ci.yml")["jobs"]["test-matrix"]["strategy"]["matrix"]["include"]
    pairs = {(leg["os"], leg["python-version"]) for leg in include}
    for os_ in ("macos-latest", "windows-latest"):
        for py in ("3.13", "3.14"):
            assert (os_, py) in pairs, f"missing {os_} / {py}"
    assert ("ubuntu-latest", "3.14") in pairs
    assert any(leg["os"] == "ubuntu-latest" and leg["scope"] == "full" for leg in include)


def test_claude_review_may_post_its_review() -> None:
    steps = _load("claude-code-review.yml")["jobs"]["claude-review"]["steps"]
    (review,) = [s for s in steps if "claude-code-action" in s.get("uses", "")]
    claude_args = (review.get("with") or {}).get("claude_args", "")
    for tool in ("Bash(gh pr comment:*)", "mcp__github_inline_comment__create_inline_comment"):
        assert tool in claude_args, f"review cannot post without {tool}"


def test_no_workflow_step_or_job_runs_on_cancel() -> None:
    """``always()`` keeps a cancelled run alive, which blocks the concurrency group.

    Every ``ci-${{ github.ref }}`` run cancelled by a newer push kept executing
    its ``if: always()`` summary steps (and the ``coverage-atlas-fused`` job),
    so the new run sat at "Expected — waiting for status" on the required
    ``lint`` check. ``!cancelled()`` still runs after a failure, not after a
    cancel.
    """
    offenders = [
        f"{path.name}:{lineno}"
        for path in sorted(_WORKFLOWS.glob("*.yml"))
        for lineno, line in enumerate(path.read_text().splitlines(), start=1)
        if "always()" in line and not line.lstrip().startswith("#")
    ]
    assert not offenders, f"use !cancelled() instead of always(): {offenders}"
