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


def test_reviews_run_on_sonnet_never_opus() -> None:
    """Policy: Claude reviews use Sonnet (or Haiku), never Opus."""
    jobs = _load("claude-code-review.yml")["jobs"]
    (step,) = [
        s for s in jobs["claude-report-run"]["steps"] if "claude-code-action" in s.get("uses", "")
    ]
    args = step["with"]["claude_args"]
    assert "--model claude-sonnet-5" in args
    assert "opus" not in args.lower()


def test_exactly_one_claude_review_per_pr() -> None:
    """One review, one sticky comment: a second reviewer saw the first one's
    comment as "already reviewed", stopped, and billed for nothing (PR #11)."""
    text = (_WORKFLOWS / "claude-code-review.yml").read_text()
    assert text.count("anthropics/claude-code-action@") == 1
    assert "plugins:" not in text


def test_review_gate_is_always_reported_and_overridable() -> None:
    """`claude-review-gate` is a required status: every PR path must set it."""
    workflow = _load("claude-code-review.yml")
    jobs = workflow["jobs"]
    text = (_WORKFLOWS / "claude-code-review.yml").read_text()
    assert text.count("claude-review-gate") >= 4
    assert "statuses" in jobs["claude-report-run"]["permissions"]
    skip_if = jobs["claude-review-gate-skip"]["if"]
    assert "sync/gitlab" in skip_if
    assert "dependabot[bot]" in skip_if
    override = jobs["claude-override"]
    assert "/claude-override" in override["if"]
    assert "author_association" in override["if"]
    # PyYAML (YAML 1.1) reads the unquoted `on:` key as True.
    assert "issue_comment" in workflow[True]


def test_review_subagents_run_in_the_foreground() -> None:
    """Headless runs end when Claude ends its turn; background subagents are lost."""
    jobs = _load("claude-code-review.yml")["jobs"]
    assert (jobs["claude-report-run"].get("env") or {}).get(
        "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS",
    ) == "1"


def test_workflow_changing_prs_get_a_red_gate() -> None:
    """Claude cannot run on a PR that edits the review workflow: red, not green."""
    jobs = _load("claude-code-review.yml")["jobs"]
    (post,) = [
        s
        for s in jobs["claude-report-run"]["steps"]
        if s.get("name") == "Post review report and set the gate"
    ]
    script = post["run"]
    not_run = script[script.index('CLAUDE_STEP_OUTCOME") == "success"') :]
    not_run = not_run[: not_run.index("sys.exit(0)")]
    assert 'gate("failure"' in not_run
    assert "/claude-override" in not_run


def test_status_descriptions_carry_no_emoji() -> None:
    """GitHub rejects 4-byte Unicode in commit-status descriptions (HTTP 422)."""
    import re

    text = (_WORKFLOWS / "claude-code-review.yml").read_text()
    for line in text.splitlines():
        if "description=" in line or 'gate("' in line:
            assert not re.search(r"[\U00010000-\U0010FFFF]", line), line.strip()
