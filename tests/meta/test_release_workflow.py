"""Release-workflow auth invariant (Phase D, task D0) + supply-chain hardening (M2).

The PyPI publish path must use exactly ONE authentication method. We chose
**trusted publishing (OIDC)**: the job keeps ``permissions: id-token: write`` and
must NOT also pass ``password: ${{ secrets.PYPI_API_TOKEN }}`` — declaring both is
the bug this guard pins (the pypa publish action auto-detects OIDC only when no
password is supplied). Enforced as a workflow-lint test so a regression that
re-adds the token (or drops the OIDC permission) fails here.

Supply-chain hardening (M2): every ``uses:`` in release.yml must be pinned to a
full 40-hex commit SHA, not a mutable version tag or branch ref.  A tag like
``@v4`` or ``@release/v1`` can be moved after the fact; in a job with
``id-token: write`` (OIDC trusted publishing) a compromised or moved tag runs
arbitrary code with access to the OIDC token.  Pinning to the immutable commit
SHA (with the human-readable tag in a trailing comment) is the GitHub-recommended
supply-chain practice.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml"


def _publish_job() -> dict:
    data = yaml.safe_load(_WORKFLOW.read_text())
    jobs = data["jobs"]
    assert "publish-pypi" in jobs, "release.yml must define a publish-pypi job"
    return jobs["publish-pypi"]


def test_pypi_publish_uses_trusted_publishing_oidc() -> None:
    """The publish job grants OIDC id-token write permission."""
    job = _publish_job()
    perms = job.get("permissions", {})
    assert perms.get("id-token") == "write", (
        "trusted publishing requires permissions.id-token: write on publish-pypi"
    )


def test_pypi_publish_does_not_also_pass_an_api_token() -> None:
    """With OIDC selected, no step may pass a PyPI API token (the two are mutually exclusive)."""
    job = _publish_job()
    offenders = [
        step.get("name", "<unnamed>")
        for step in job.get("steps", [])
        if "password" in (step.get("with") or {})
    ]
    assert not offenders, (
        "publish-pypi uses trusted publishing (OIDC) — remove the "
        f"`with: password: ...` from: {offenders}. Declaring both id-token and a "
        "PYPI_API_TOKEN is the auth double-declaration bug."
    )


# ---------------------------------------------------------------------------
# Supply-chain hardening (M2): every uses: must be a 40-hex commit SHA
# ---------------------------------------------------------------------------

_SHA40_RE = re.compile(r"@[0-9a-f]{40}\b")


def _collect_uses(workflow_path: Path) -> list[str]:
    """Return every ``uses:`` value found in the workflow (all jobs, all steps)."""
    data = yaml.safe_load(workflow_path.read_text())
    found: list[str] = []
    # top-level uses (reusable workflow call)
    if "uses" in data:
        found.append(data["uses"])
    for job in (data.get("jobs") or {}).values():
        if "uses" in job:
            found.append(job["uses"])
        for step in job.get("steps") or []:
            if "uses" in step:
                found.append(step["uses"])
    return found


def test_all_uses_pinned_to_commit_sha() -> None:
    """Every ``uses:`` in release.yml must reference a full 40-hex commit SHA.

    Mutable tags (``@v4``, ``@release/v1``) or branch refs can be moved after
    publication.  In a job that holds ``id-token: write`` (OIDC trusted
    publishing) a moved tag can run arbitrary code with access to the OIDC
    token.  Pin to the immutable commit SHA and record the human-readable
    version in a trailing comment.
    """
    uses_values = _collect_uses(_WORKFLOW)
    unpinned = [u for u in uses_values if not _SHA40_RE.search(u)]
    assert not unpinned, (
        "The following uses: lines in release.yml are NOT pinned to a 40-hex "
        "commit SHA — replace each @tag with @<sha>  # tag:\n"
        + "\n".join(f"  {u}" for u in unpinned)
    )
