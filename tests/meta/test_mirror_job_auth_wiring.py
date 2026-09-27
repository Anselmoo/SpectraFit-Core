"""Behavioural checks for the mirror jobs' git auth setup.

The GitHub mirror may be PRIVATE (the test phase before the public restart runs
against a private repository), so every job that talks to github.com needs its
token for FETCHES too, not only for pushes — and must still never write a
token into a remote URL or ``.git/config`` (CWE-522).

Rather than grepping the YAML, these tests run each job's real ``script:``
entries — everything up to (not including) the Python script it hands over to
— in ``bash`` inside a throwaway git repository with fake CI variables, then ask
git itself which ``http.extraheader`` it would send to which host
(``git config --get-urlmatch``). That is exactly what the later ``git
fetch``/``git push`` would see.
"""

from __future__ import annotations

import base64
import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_BACKPORT_YML = _ROOT / ".gitlab" / "75-backport.yml"
_PUBLISH_YML = _ROOT / ".gitlab" / "70-publish.yml"

_GITLAB = "https://gitlab.example"
_GITHUB_URL = "https://github.com/Anselmoo/SpectraFit-Core.git"
_BACKPORT_TOKEN = "fake-backport-token-0123"
_GITHUB_TOKEN = "fake-github-token-4567"
_GITHUB_ED25519 = (
    "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
)


class _TolerantLoader(yaml.SafeLoader):
    """SafeLoader that tolerates GitLab's `!reference` tag."""


_TolerantLoader.add_constructor("!reference", lambda _loader, _node: None)


def _script(path: Path, job: str) -> list[str]:
    doc = yaml.load(path.read_text(encoding="utf-8"), Loader=_TolerantLoader)
    entries = doc[job]["script"]
    assert all(isinstance(entry, str) for entry in entries), job
    return entries


def _setup_entries(entries: list[str], stop_marker: str) -> list[str]:
    """Every entry before the first one containing `stop_marker`."""
    for index, entry in enumerate(entries):
        if stop_marker in entry:
            return entries[:index]
    raise AssertionError(f"{stop_marker!r} not found in job script")


def _run(
    tmp_path: Path,
    entries: list[str],
    extra_env: dict[str, str],
) -> tuple[subprocess.CompletedProcess[str], Path]:
    repo = tmp_path / "checkout"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    probe = "\n".join(
        [
            'echo "COUNT=${GIT_CONFIG_COUNT:-}"',
            f'echo "GITLAB_HEADER=$(git config --get-urlmatch http.extraheader {_GITLAB}/anhahn/spectrafit-core.git || true)"',
            f'echo "GITHUB_HEADER=$(git config --get-urlmatch http.extraheader {_GITHUB_URL} || true)"',
            'echo "SSH_COMMAND=${GIT_SSH_COMMAND:-}"',
            'echo "PUSH_URL=$(git remote get-url github-push 2>/dev/null || true)"',
        ],
    )
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "GIT_CONFIG_NOSYSTEM": "1",
        "CI_SERVER_URL": _GITLAB,
        "CI_PROJECT_URL": f"{_GITLAB}/anhahn/spectrafit-core",
        **extra_env,
    }
    result = subprocess.run(
        ["bash", "-e", "-c", "\n".join([*entries, probe])],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, repo


def _probe(stdout: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.isupper():
            values[key] = value
    return values


def _basic_credentials(header: str) -> str:
    prefix = "Authorization: Basic "
    assert header.startswith(prefix), header
    return base64.b64decode(header[len(prefix) :]).decode()


def _assert_no_token_persisted(repo: Path) -> None:
    config = (repo / ".git" / "config").read_text(encoding="utf-8")
    remotes = subprocess.run(
        ["git", "remote", "-v"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for token in (_BACKPORT_TOKEN, _GITHUB_TOKEN):
        encoded = base64.b64encode(token.encode()).decode()
        for text in (config, remotes):
            assert token not in text
            assert encoded not in text


# ---------------------------------------------------------------------------
# backport:github — GitLab push auth AND GitHub fetch auth, one header each.
# ---------------------------------------------------------------------------


def test_backport_job_sets_both_headers_each_scoped_to_its_own_host(tmp_path: Path) -> None:
    entries = _setup_entries(
        _script(_BACKPORT_YML, "backport:github"),
        "scripts/backport_from_github.py",
    )
    result, repo = _run(
        tmp_path,
        entries,
        {"BACKPORT_TOKEN": _BACKPORT_TOKEN, "GITHUB_TOKEN": _GITHUB_TOKEN},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    probe = _probe(result.stdout)

    assert probe["COUNT"] == "2"
    # Each host gets exactly its own credential — never the other one.
    assert _basic_credentials(probe["GITLAB_HEADER"]) == f"backport-token:{_BACKPORT_TOKEN}"
    assert _basic_credentials(probe["GITHUB_HEADER"]) == f"x-access-token:{_GITHUB_TOKEN}"
    _assert_no_token_persisted(repo)


# ---------------------------------------------------------------------------
# publish:github / publish:github:fast — authenticated fetch + deploy-key land.
# ---------------------------------------------------------------------------

_PUBLISH_JOBS = ("publish:github", "publish:github:fast")


def _fake_ssh_path(tmp_path: Path) -> str:
    """PATH with a stub `ssh`, so the image's tool check passes on any host."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "ssh"
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    return f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


def _publish_setup(job: str) -> list[str]:
    entries = _script(_PUBLISH_YML, job)
    stop = "git fetch github main" if job == "publish:github:fast" else "scripts/publish_sync.py"
    return _setup_entries(entries, stop)


@pytest.mark.parametrize("job", _PUBLISH_JOBS)
def test_publish_jobs_authenticate_fetches_and_land_with_the_pinned_deploy_key(
    tmp_path: Path,
    job: str,
) -> None:
    deploy_key = tmp_path / "deploy_key"
    # GitLab's File variable stores this WITHOUT a trailing newline (glab
    # strips it) — reproduce that so the test actually exercises the
    # newline-normalisation copy, not a file that was already well-formed.
    deploy_key.write_text("fake private key", encoding="utf-8")
    deploy_key.chmod(0o644)

    result, repo = _run(
        tmp_path,
        _publish_setup(job),
        {
            "PATH": _fake_ssh_path(tmp_path),
            "GITHUB_TOKEN": _GITHUB_TOKEN,
            "GITHUB_DEPLOY_KEY": str(deploy_key),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    probe = _probe(result.stdout)

    assert _basic_credentials(probe["GITHUB_HEADER"]) == f"x-access-token:{_GITHUB_TOKEN}"
    assert probe["GITLAB_HEADER"] == ""  # the GitHub token never goes to GitLab
    assert probe["PUSH_URL"] == "git@github.com:Anselmoo/SpectraFit-Core.git"

    ssh_command = probe["SSH_COMMAND"]
    # The job must never point ssh straight at the raw File-variable path —
    # it normalises into its own copy first (a newline-less key can make
    # OpenSSH reject the file as "invalid format").
    assert f"-i '{deploy_key}'" not in ssh_command
    deploy_key_file = Path(ssh_command.split("-i '", 1)[1].split("'", 1)[0])
    assert deploy_key_file != deploy_key
    for option in ("IdentitiesOnly=yes", "BatchMode=yes", "StrictHostKeyChecking=yes"):
        assert option in ssh_command
    known_hosts = Path(ssh_command.split("UserKnownHostsFile='", 1)[1].split("'", 1)[0])
    assert known_hosts.read_text(encoding="utf-8").splitlines() == [_GITHUB_ED25519]
    # The normalised copy carries the trailing newline the original lacked,
    # and only the copy — never the original File variable — is chmod'd.
    assert deploy_key_file.read_text(encoding="utf-8") == "fake private key\n"
    assert stat.S_IMODE(deploy_key_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(deploy_key.stat().st_mode) == 0o644
    _assert_no_token_persisted(repo)


@pytest.mark.parametrize("job", _PUBLISH_JOBS)
def test_publish_jobs_fail_loudly_without_the_deploy_key(tmp_path: Path, job: str) -> None:
    result, _repo = _run(
        tmp_path,
        _publish_setup(job),
        {"PATH": _fake_ssh_path(tmp_path), "GITHUB_TOKEN": _GITHUB_TOKEN},
    )
    assert result.returncode != 0
    assert "GITHUB_DEPLOY_KEY" in result.stderr
