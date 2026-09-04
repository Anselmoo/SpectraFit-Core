"""Structural checks that .gitlab/70-publish.yml wires both publish jobs to
the shared scripts. Does NOT execute the jobs (that requires a real GitLab
pipeline run — see the design spec's testing plan) — only pins that the YAML
references the extracted scripts by path, so a future edit can't silently
reintroduce inline-script drift between publish:github and
publish:github:fast.
"""

from __future__ import annotations

from pathlib import Path

_PUBLISH_YML = Path(__file__).resolve().parents[2] / ".gitlab" / "70-publish.yml"


def _text() -> str:
    return _PUBLISH_YML.read_text(encoding="utf-8")


def test_publish_github_calls_shared_snapshot_script() -> None:
    assert "scripts/publish_snapshot.sh" in _text()


def test_publish_github_fast_job_exists_with_needs_empty() -> None:
    text = _text()
    assert "publish:github:fast:" in text
    fast_block = text.split("publish:github:fast:", 1)[1]
    assert "needs: []" in fast_block
    assert "dependencies: []" in fast_block


def test_publish_github_fast_calls_gate_then_shared_script() -> None:
    text = _text()
    fast_block = text.split("publish:github:fast:", 1)[1]
    gate_idx = fast_block.find("fast_lane_gate.py")
    snapshot_idx = fast_block.find("publish_snapshot.sh")
    assert gate_idx != -1, "expected publish:github:fast to call fast_lane_gate.py"
    assert snapshot_idx != -1, "expected publish:github:fast to call publish_snapshot.sh"
    assert gate_idx < snapshot_idx, "the diff-gate must run BEFORE the publish script"


def test_both_jobs_share_the_same_rules() -> None:
    text = _text()
    assert text.count("if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'") == 2
