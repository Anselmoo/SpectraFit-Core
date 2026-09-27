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


def _load() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text())


def _jobs() -> dict:
    return _load()["jobs"]


def _job(name: str) -> dict:
    jobs = _jobs()
    assert name in jobs, f"release.yml must define a {name} job"
    return jobs[name]


def _publish_job() -> dict:
    return _job("publish-pypi")


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


# ---------------------------------------------------------------------------
# Trigger patterns: tag pushes (incl. rc/a/b pre-releases) + a tag-free
# workflow_dispatch build dry run.
# ---------------------------------------------------------------------------


def _triggers() -> dict:
    data = _load()
    # PyYAML (YAML 1.1) parses the unquoted `on:` key as the boolean True.
    assert True in data, "release.yml must define an `on:` trigger block"
    return data[True]


def test_trigger_is_semver_tag_push_and_workflow_dispatch() -> None:
    """The only triggers are `push: tags: v*.*.*` and `workflow_dispatch`."""
    triggers = _triggers()
    assert set(triggers) == {"push", "workflow_dispatch"}, (
        f"unexpected top-level triggers: {sorted(triggers)}"
    )
    assert triggers["push"] == {"tags": ["v*.*.*"]}, (
        "push trigger must be scoped to `tags: ['v*.*.*']` only"
    )


def test_tag_pattern_matches_prerelease_tags() -> None:
    """The `v*.*.*` glob must also match rc/a/b pre-release tags like v0.1.0rc1."""
    import fnmatch

    pattern = _triggers()["push"]["tags"][0]
    for tag in ("v0.1.0", "v1.2.3", "v0.1.0rc1", "v0.1.0a1", "v0.1.0b2"):
        assert fnmatch.fnmatch(tag, pattern), f"{tag!r} does not match {pattern!r}"


def test_workflow_dispatch_has_no_tag_input() -> None:
    """workflow_dispatch is the tag-free build dry run -- no `tag` input."""
    dispatch = _triggers()["workflow_dispatch"]
    assert not dispatch, (
        f"workflow_dispatch must take no inputs (tag-free build dry run), got: {dispatch}"
    )


# ---------------------------------------------------------------------------
# publish-testpypi: tag-push only.
# ---------------------------------------------------------------------------


def test_publish_testpypi_is_tag_push_only() -> None:
    job = _job("publish-testpypi")
    assert job.get("if") == "startsWith(github.ref, 'refs/tags/v')", (
        "publish-testpypi must be gated on `startsWith(github.ref, 'refs/tags/v')` "
        f"(a tag push), got: {job.get('if')!r}"
    )


def test_verify_testpypi_needs_publish_testpypi() -> None:
    job = _job("verify-testpypi")
    needs = job.get("needs")
    needs_set = {needs} if isinstance(needs, str) else set(needs or [])
    assert "publish-testpypi" in needs_set, (
        f"verify-testpypi must need publish-testpypi, got needs={needs!r}"
    )


# ---------------------------------------------------------------------------
# publish-pypi: excludes rc/a/b tags, needs verify-testpypi, no opt-in var.
# ---------------------------------------------------------------------------


def test_publish_pypi_needs_verify_testpypi() -> None:
    job = _publish_job()
    needs = job.get("needs")
    needs_set = {needs} if isinstance(needs, str) else set(needs or [])
    assert "verify-testpypi" in needs_set, (
        f"publish-pypi must need verify-testpypi, got needs={needs!r}"
    )


def test_publish_pypi_runs_only_for_final_versions() -> None:
    """publish-pypi is gated on version-guard's metadata verdict, not on the tag text."""
    job = _publish_job()
    condition = job.get("if") or ""
    assert "startsWith(github.ref, 'refs/tags/v')" in condition
    assert "needs.version-guard.outputs.is_prerelease == 'false'" in condition, (
        f"publish-pypi must run only when version-guard reports a final version, got: {condition!r}"
    )


def test_no_publish_pypi_opt_in_variable_anywhere() -> None:
    """The old `vars.PUBLISH_PYPI` opt-in gate must be gone entirely."""
    text = _WORKFLOW.read_text()
    assert "PUBLISH_PYPI" not in text, (
        "release.yml still references the removed PUBLISH_PYPI opt-in variable"
    )


# ---------------------------------------------------------------------------
# github-release: prerelease wiring for rc/a/b tags, final tags need publish-pypi.
# ---------------------------------------------------------------------------


def test_github_release_needs_publish_pypi_and_verify_testpypi() -> None:
    job = _job("github-release")
    needs = set(job.get("needs") or [])
    assert "publish-pypi" in needs, "github-release must need publish-pypi"
    assert "verify-testpypi" in needs, "github-release must need verify-testpypi"


def test_github_release_tolerates_skipped_publish_pypi_for_prereleases() -> None:
    """rc/a/b tags skip publish-pypi (by design); github-release must still run."""
    job = _job("github-release")
    condition = job.get("if") or ""
    assert "always()" in condition, (
        "github-release's `if` must use always() so a *skipped* (not failed) "
        f"publish-pypi doesn't block the release, got: {condition!r}"
    )
    assert "needs.publish-pypi.result == 'success'" in condition
    assert "needs.publish-pypi.result == 'skipped'" in condition
    assert "needs.verify-testpypi.result == 'success'" in condition


def test_github_release_prerelease_comes_from_version_guard() -> None:
    job = _job("github-release")
    steps = job.get("steps") or []
    release_steps = [s for s in steps if "action-gh-release" in s.get("uses", "")]
    assert release_steps, "github-release must have a softprops/action-gh-release step"
    prerelease = (release_steps[0].get("with") or {}).get("prerelease")
    assert prerelease == "${{ needs.version-guard.outputs.is_prerelease }}", (
        f"prerelease must be version-guard's is_prerelease output, got: {prerelease!r}"
    )
    assert "needs.version-guard.result == 'success'" in (job.get("if") or "")


def test_github_release_generates_notes_and_attaches_dist_and_sbom() -> None:
    job = _job("github-release")
    steps = job.get("steps") or []
    release_steps = [s for s in steps if "action-gh-release" in s.get("uses", "")]
    assert release_steps
    with_ = release_steps[0].get("with") or {}
    assert with_.get("generate_release_notes") is True
    files = with_.get("files") or ""
    assert "dist/*" in files
    assert "sbom.spdx.json" in files


# ---------------------------------------------------------------------------
# version-guard: every upload waits for "artifact metadata == tag".
# ---------------------------------------------------------------------------

_UPLOAD_JOBS = ("attest", "publish-testpypi", "publish-pypi", "github-release")


def _needs(job: dict) -> set[str]:
    needs = job.get("needs")
    return {needs} if isinstance(needs, str) else set(needs or [])


def _transitive_needs(name: str) -> set[str]:
    jobs = _jobs()
    seen: set[str] = set()
    stack = [name]
    while stack:
        for dep in _needs(jobs[stack.pop()]):
            if dep not in seen:
                seen.add(dep)
                stack.append(dep)
    return seen


def test_version_guard_needs_build_and_exports_outputs() -> None:
    job = _job("version-guard")
    assert "build" in _needs(job)
    outputs = job.get("outputs") or {}
    assert set(outputs) >= {"version", "is_prerelease"}, outputs


def test_every_upload_job_depends_on_version_guard() -> None:
    missing = [name for name in _UPLOAD_JOBS if "version-guard" not in _transitive_needs(name)]
    assert not missing, f"upload jobs not (transitively) behind version-guard: {missing}"


def test_no_tag_text_prerelease_logic_left() -> None:
    """Pre-release detection lives in version-guard (packaging), not in contains() on the tag."""
    text = _WORKFLOW.read_text()
    assert "contains(" not in text, (
        "release.yml still decides pre-release status with contains(); use "
        "needs.version-guard.outputs.is_prerelease instead"
    )


def _guard_script() -> str:
    steps = _job("version-guard").get("steps") or []
    (step,) = [s for s in steps if s.get("id") == "guard"]
    assert step.get("shell") == "python"
    return step["run"]


def _write_dists(dist: Path, wheel_versions: list[str], sdist_version: str) -> None:
    import io
    import tarfile
    import zipfile

    dist.mkdir()
    for i, version in enumerate(wheel_versions):
        with zipfile.ZipFile(dist / f"spectrafit_core-0-cp313-plat{i}.whl", "w") as zf:
            zf.writestr(
                f"spectrafit_core-{version}.dist-info/METADATA",
                f"Metadata-Version: 2.4\nName: spectrafit-core\nVersion: {version}\n",
            )
    payload = f"Metadata-Version: 2.4\nName: spectrafit-core\nVersion: {sdist_version}\n".encode()
    with tarfile.open(dist / "spectrafit_core-0.tar.gz", "w:gz") as tf:
        info = tarfile.TarInfo(f"spectrafit_core-{sdist_version}/PKG-INFO")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))


def _run_guard(tmp_path: Path, tag: str) -> tuple[int, str, str]:
    import os
    import subprocess
    import sys

    out = tmp_path / "github_output"
    out.touch()
    env = {**os.environ, "EXPECTED_TAG": tag, "GITHUB_OUTPUT": str(out)}
    proc = subprocess.run(
        [sys.executable, "-c", _guard_script()],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr, out.read_text()


def test_version_guard_accepts_matching_prerelease(tmp_path: Path) -> None:
    _write_dists(tmp_path / "dist", ["0.1.0rc1", "0.1.0rc1", "0.1.0rc1"], "0.1.0rc1")
    code, log, outputs = _run_guard(tmp_path, "v0.1.0rc1")
    assert code == 0, log
    assert "version=0.1.0rc1" in outputs
    assert "is_prerelease=true" in outputs


def test_version_guard_marks_final_release(tmp_path: Path) -> None:
    _write_dists(tmp_path / "dist", ["0.1.0", "0.1.0"], "0.1.0")
    code, log, outputs = _run_guard(tmp_path, "v0.1.0")
    assert code == 0, log
    assert "is_prerelease=false" in outputs


def test_version_guard_rejects_tag_ahead_of_bump(tmp_path: Path) -> None:
    """Tagging v0.1.0rc1 on a tree still at 0.1.0 must stop before any upload."""
    _write_dists(tmp_path / "dist", ["0.1.0", "0.1.0", "0.1.0"], "0.1.0")
    code, log, outputs = _run_guard(tmp_path, "v0.1.0rc1")
    assert code != 0
    assert "0.1.0rc1" in log
    assert outputs == ""


def test_version_guard_rejects_one_divergent_artifact(tmp_path: Path) -> None:
    _write_dists(tmp_path / "dist", ["0.1.0rc1", "0.1.0rc2"], "0.1.0rc1")
    code, log, _ = _run_guard(tmp_path, "v0.1.0rc1")
    assert code != 0
    assert "0.1.0rc2" in log


# ---------------------------------------------------------------------------
# Wheel build: every supported CPython on every platform.
# ---------------------------------------------------------------------------


def _build_wheels_step() -> dict:
    steps = _job("build-wheels").get("steps") or []
    (step,) = [s for s in steps if "maturin-action" in s.get("uses", "")]
    return step


def test_linux_wheels_build_in_manylinux_2_28() -> None:
    """manylinux2014 (CentOS 7: cmake 2.8, gfortran 4.8) cannot build netlib LAPACK."""
    with_ = _build_wheels_step().get("with") or {}
    assert str(with_.get("manylinux")) == "2_28", with_.get("manylinux")
    assert "dnf install" in (with_.get("before-script-linux") or "")


def test_every_wheel_leg_builds_for_all_supported_pythons() -> None:
    include = _job("build-wheels")["strategy"]["matrix"]["include"]
    assert {leg["os"] for leg in include} == {"ubuntu-latest", "macos-latest", "windows-latest"}
    for leg in include:
        interpreters = leg.get("interpreters", "")
        assert interpreters == "--find-interpreter" or (
            "python3.13" in interpreters and "python3.14" in interpreters
        ), leg
    args = (_build_wheels_step().get("with") or {}).get("args", "")
    assert "${{ matrix.interpreters }}" in args, args


def test_verify_testpypi_covers_every_os_and_python() -> None:
    matrix = _job("verify-testpypi")["strategy"]["matrix"]
    assert set(matrix["os"]) == {"ubuntu-latest", "macos-latest", "windows-latest"}
    assert set(matrix["python-version"]) == {"3.13", "3.14"}
