"""Renovate is the one update bot, and its PRs cannot become a review bypass.

* Renovate replaced Dependabot for every ecosystem, including the GitLab CI
  image: each ``ARG *_VERSION`` in ``.gitlab/docker/Dockerfile.ci`` carries a
  ``# renovate:`` annotation (``customManagers:dockerfileVersions``).
* Bot PRs skip the paid Claude review only when the bot itself opened them
  from a branch of this repository -- a fork branch named ``renovate/...``
  must still be reviewed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_CONFIG = _ROOT / ".github" / "renovate.json"
_DOCKERFILE = _ROOT / ".gitlab" / "docker" / "Dockerfile.ci"


def test_renovate_is_the_only_update_bot() -> None:
    config = json.loads(_CONFIG.read_text())
    assert "helpers:pinGitHubActionDigests" in config["extends"]
    assert "customManagers:dockerfileVersions" in config["extends"]
    assert config["vulnerabilityAlerts"]["enabled"] is True
    assert not (_ROOT / ".github" / "dependabot.yml").exists()


def test_every_image_version_arg_is_annotated_for_renovate() -> None:
    lines = _DOCKERFILE.read_text().splitlines()
    header = lines[: next(i for i, line in enumerate(lines) if line.startswith("FROM "))]
    for i, line in enumerate(header):
        if re.match(r"ARG \w+_VERSION=", line):
            assert header[i - 1].startswith("# renovate: datasource="), f"unannotated: {line}"


def test_bot_review_skip_requires_the_bot_author_and_a_same_repo_branch() -> None:
    text = (_ROOT / ".github" / "workflows" / "claude-code-review.yml").read_text()
    for bot in ("renovate[bot]", "dependabot[bot]"):
        assert f"github.event.pull_request.user.login == '{bot}'" in text
    assert text.count("github.event.pull_request.head.repo.full_name == github.repository") >= 3


def test_sha_pinned_image_downloads_are_checked_on_github() -> None:
    workflow = yaml.safe_load((_ROOT / ".github" / "workflows" / "docker-pins.yml").read_text())
    assert ".gitlab/docker/Dockerfile.ci" in workflow[True]["pull_request"]["paths"]
    script = workflow["jobs"]["sha256"]["steps"][1]["run"]
    for arg in ("LLVM_COV_SHA256", "LYCHEE_SHA256"):
        assert arg in script
