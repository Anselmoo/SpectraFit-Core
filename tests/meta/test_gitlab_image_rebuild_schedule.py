"""The weekly CI-image rebuild schedule runs build:ci-image and nothing else.

A GitLab pipeline schedule on ``main`` matches every ``main`` rule, so without
a guard it would start the whole ~75-minute battery and the deep benchmark.
The schedule sets ``CI_IMAGE_REBUILD=true``; the two shared rule anchors and
every job with its own rules start with ``when: never`` for it, and only
``build:ci-image`` runs on it.
"""

from __future__ import annotations

import re
from pathlib import Path

_GITLAB = Path(__file__).resolve().parents[2] / ".gitlab"
_GUARD = re.compile(r"""- if: '\$CI_IMAGE_REBUILD == "true"'\n\s+when: never""")


def _rules_blocks() -> dict[str, str]:
    """{"file:job": rules text} for every job or anchor with a `rules:` block."""
    blocks: dict[str, str] = {}
    for path in sorted(_GITLAB.glob("*.yml")):
        text = path.read_text()
        for match in re.finditer(r"(?ms)^([.A-Za-z0-9_:-]+):\s*\n(.*?)(?=^\S|\Z)", text):
            name, body = match.group(1), match.group(2)
            rules = re.search(r"(?ms)^  rules:[ \t]*(.*?)(?=^  [a-z_]+:|\Z)", body)
            if rules is not None:
                blocks[f"{path.name}:{name}"] = rules.group(1)
    return blocks


def test_shared_rule_anchors_carry_the_guard() -> None:
    blocks = _rules_blocks()
    for anchor in ("00-defaults.yml:.rules_default", "00-defaults.yml:.rules_full_only"):
        assert _GUARD.search(blocks[anchor]), anchor


def test_every_other_job_is_guarded_or_inherits_an_anchor() -> None:
    offenders = []
    for key, rules in _rules_blocks().items():
        name = key.split(":", 1)[1]
        if name.startswith(".") or name == "build:ci-image":
            continue
        inherits = "!reference [.rules_default" in rules or "!reference [.rules_full_only" in rules
        mr_only = (
            rules.strip().startswith("- if: '$CI_PIPELINE_SOURCE == \"merge_request_event\"'")
            and "\n    - if" not in rules.strip()
        )
        if not (_GUARD.search(rules) or (inherits and "schedule" not in rules) or mr_only):
            offenders.append(key)
    assert not offenders, f"these jobs would run on the image-rebuild schedule: {offenders}"


def test_build_ci_image_runs_on_the_schedule_and_has_no_version_copies() -> None:
    text = (_GITLAB / "docker-build.yml").read_text()
    rules = _rules_blocks()["docker-build.yml:build:ci-image"]
    assert """- if: '$CI_IMAGE_REBUILD == "true"'""" in rules
    assert "when: never" not in rules.split("changes:")[0]
    # Versions live only in Dockerfile.ci's ARG defaults (Renovate-managed).
    code = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    assert not any("--build-arg" in line for line in code)
