"""Structural checks that .gitlab/70-publish.yml wires all three publish jobs
to the shared scripts. Does NOT execute the jobs (that requires a real GitLab
pipeline run — see the design spec's testing plan) — only pins that the YAML
references the extracted scripts by path, so a future edit can't silently
reintroduce inline-script drift between the jobs, or accidentally point the
normal (append-only, PR-based) sync path at the history-discarding orphan
snapshot script (or vice versa).
"""

from __future__ import annotations

import re
from pathlib import Path

_PUBLISH_YML = Path(__file__).resolve().parents[2] / ".gitlab" / "70-publish.yml"

# Matches a job's top-level YAML key, e.g. "publish:github:fast:" at column 0
# (job names themselves contain colons, so the whole run up to the final
# `:<eol>` is the name) — never a comment line or an indented nested key.
_JOB_HEADER_RE = re.compile(r"^(?!#)([A-Za-z0-9_.:-]+):[ \t]*$", re.MULTILINE)


def _text() -> str:
    return _PUBLISH_YML.read_text(encoding="utf-8")


def _job_block(text: str, job_name: str) -> str:
    """Return the raw YAML for `job_name`'s block (header line through the
    line before the next top-level job, or end of file)."""
    headers = [(m.start(), m.group(1)) for m in _JOB_HEADER_RE.finditer(text)]
    headers.sort(key=lambda item: item[0])
    for index, (start, name) in enumerate(headers):
        if name != job_name:
            continue
        end = headers[index + 1][0] if index + 1 < len(headers) else len(text)
        return text[start:end]
    raise AssertionError(f"job {job_name!r} not found in {_PUBLISH_YML}")


def test_all_three_publish_jobs_exist() -> None:
    text = _text()
    for job in ("publish:github", "publish:github:fast", "publish:github:reset"):
        assert _job_block(text, job), f"expected a non-empty block for {job!r}"


def test_publish_github_calls_publish_sync_not_the_orphan_snapshot() -> None:
    block = _job_block(_text(), "publish:github")
    assert "scripts/publish_sync.py" in block
    assert "scripts/publish_snapshot.sh" not in block


def test_publish_github_fast_job_exists_with_needs_empty() -> None:
    block = _job_block(_text(), "publish:github:fast")
    assert "needs: []" in block
    assert "dependencies: []" in block


def test_publish_github_fast_calls_gate_then_publish_sync() -> None:
    block = _job_block(_text(), "publish:github:fast")
    gate_idx = block.find("fast_lane_gate.py")
    sync_idx = block.find("publish_sync.py")
    assert gate_idx != -1, "expected publish:github:fast to call fast_lane_gate.py"
    assert sync_idx != -1, "expected publish:github:fast to call publish_sync.py"
    assert gate_idx < sync_idx, "the diff-gate must run BEFORE the sync script"
    assert "scripts/publish_snapshot.sh" not in block


def test_publish_github_reset_job_is_manual_and_calls_the_orphan_snapshot_script() -> None:
    text = _text()
    block = _job_block(text, "publish:github:reset")
    assert "when: manual" in block
    assert "scripts/publish_snapshot.sh" in block
    # The reset job is the only one that still needs the shell-level token
    # header injection (publish_snapshot.sh's own CWE-522 pattern) — the
    # normal sync path injects it inside scripts/publish_sync.py itself.
    assert "GIT_CONFIG_VALUE_0" in block


def test_normal_sync_jobs_do_not_call_the_actions_purge() -> None:
    """The stale-Actions-run purge only makes sense right after the orphan
    snapshot discards history — it must not run on the append-only sync
    path, which never discards anything."""
    text = _text()
    for job in ("publish:github", "publish:github:fast"):
        block = _job_block(text, job)
        assert "purge_github_actions_runs.py" not in block


def test_all_three_jobs_share_the_same_rules() -> None:
    assert _text().count("if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'") == 3


def test_all_three_jobs_share_the_same_resource_group() -> None:
    text = _text()
    for job in ("publish:github", "publish:github:fast", "publish:github:reset"):
        assert "resource_group: publish_github" in _job_block(text, job)


def _script_entries(block: str) -> list[str]:
    """The `- |` entries of a job block, each as its dedented shell text."""
    entries: list[str] = []
    for chunk in block.split("    - |\n")[1:]:
        lines = [line for line in chunk.splitlines() if line.startswith("      ")]
        entries.append("\n".join(line[6:] for line in lines))
    return entries


def test_auth_and_land_setup_is_identical_in_both_sync_jobs() -> None:
    """The setup is duplicated inline (see the file's header comment on why no
    anchor) — pin the two copies so they cannot drift apart."""
    text = _text()
    full = _script_entries(_job_block(text, "publish:github"))
    fast = _script_entries(_job_block(text, "publish:github:fast"))
    land_index = next(i for i, entry in enumerate(full) if "github-push" in entry)
    setup = full[: land_index + 1]
    assert fast[: land_index + 1] == setup
    assert any("GITHUB_DEPLOY_KEY" in entry for entry in setup)
    assert any("http.https://github.com/.extraheader" in entry for entry in setup)


def test_sync_jobs_never_embed_a_token_in_a_remote_url() -> None:
    text = _text()
    for job in ("publish:github", "publish:github:fast"):
        block = _job_block(text, job)
        assert not re.search(r"https://[^\s\"']*@github\.com", block), job
