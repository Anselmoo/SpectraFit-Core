"""Tests for scripts/publish_sync.py — the GitLab -> GitHub append-only sync.

Pure-git plumbing (tree building, commit-tree, rev-parse, push) is exercised
against a throwaway local "repo" + a throwaway local bare "remote" — no
network needed, since `git push`/`git fetch` work fine against a local bare
repo path. The GitHub REST layer is exercised with `_api_request` (or the
higher-level API helpers) mocked out — no network call is ever made from
these tests.

The anonymity contract (bot author + committer, fixed message, only the
`GitLab-Commit:` trailer from GitLab) and the fast-forward landing are pinned
end-to-end against a local bare "mirror": see the `main()` tests at the end.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import publish_sync as sync  # ty: ignore[unresolved-import]

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "publish_sync.py"


def _git(
    repo: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")


def _write(repo: Path, files: dict[str, str]) -> None:
    for rel_path, content in files.items():
        path = repo / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _commit(repo: Path, files: dict[str, str], message: str) -> str:
    _write(repo, files)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _make_repo_with_remote(tmp_path: Path) -> tuple[Path, Path]:
    """A local "gitlab" checkout plus a local bare "remote" standing in for
    the GitHub mirror, already carrying one published commit."""
    remote = tmp_path / "remote.git"
    # -b main: independent of the caller's init.defaultBranch (git <2.28
    # defaults to "master", and even on newer git a global config can set
    # anything). Without it the bare remote's HEAD may not be "main" at all,
    # which _race_remote_main's clone below then has no branch to push.
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))

    repo = tmp_path / "gitlab"
    _init_repo(repo)
    _commit(
        repo,
        {
            "README.md": "hello\n",
            ".github/workflows/ci.yml": "name: ci\n",
        },
        "base",
    )
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "origin", "main:main")
    return repo, remote


# --------------------------------------------------------------------------
# Pure logic
# --------------------------------------------------------------------------

_BOT = ("spectrafit-core-sync[bot]", "334580965+spectrafit-core-sync[bot]@users.noreply.github.com")


def test_parse_sync_trailer_finds_the_value() -> None:
    message = "sync: gitlab main\n\nSome body.\n\nGitLab-Commit: " + "a" * 40
    assert sync.parse_sync_trailer(message) == "a" * 40


def test_parse_sync_trailer_returns_none_when_absent() -> None:
    assert sync.parse_sync_trailer("Initial commit\n") is None


def test_build_sync_message_is_fixed_text_plus_trailer_only() -> None:
    sha = "b" * 40
    subject, body = sync.build_sync_message(sha)
    # The subject is fully generic — no SHA, not even a short one.
    assert subject == "sync: gitlab main"
    assert sha[:7] not in subject
    # The body is the fixed text, a blank line, and the trailer — nothing else.
    assert body == f"{sync._SYNC_TEXT}\n\n{sync.SYNC_TRAILER}: {sha}"
    assert sync.parse_sync_trailer(body) == sha
    # The only place the GitLab SHA appears at all is the trailer line.
    lines_with_sha = [line for line in f"{subject}\n\n{body}".splitlines() if sha[:7] in line]
    assert lines_with_sha == [f"{sync.SYNC_TRAILER}: {sha}"]


def test_excluded_tracked_paths_matches_shared_patterns() -> None:
    paths = [
        "analysis/crates/PREFLIGHT.md",
        ".github/workflows/ci.yml",
        "docs/superpowers/plans/x.md",
        "pyproject.toml",
    ]
    assert sync.excluded_tracked_paths(paths) == [
        "analysis/crates/PREFLIGHT.md",
        "docs/superpowers/plans/x.md",
    ]


def test_sync_needed_true_when_trees_differ() -> None:
    assert sync.sync_needed("aaa", "bbb") is True


def test_sync_needed_false_when_trees_equal() -> None:
    assert sync.sync_needed("aaa", "aaa") is False


def test_required_check_contexts_reads_only_status_check_rules() -> None:
    rules = [
        {"type": "pull_request", "parameters": {"required_approving_review_count": 0}},
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [{"context": "lint"}, {"context": "build-and-test"}],
            },
        },
        {
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": "lint"}]},
        },
    ]
    assert sync.required_check_contexts(rules) == ["lint", "build-and-test"]
    assert sync.required_check_contexts([{"type": "deletion"}]) == []


def test_evaluate_checks_success_failure_and_pending() -> None:
    done = {"name": "lint", "status": "completed", "conclusion": "success"}
    skipped = {"name": "web", "status": "completed", "conclusion": "skipped"}
    running = {"name": "web", "status": "in_progress", "conclusion": None}
    failed = {"name": "web", "status": "completed", "conclusion": "failure"}
    assert sync.evaluate_checks(["lint", "web"], [done, skipped], []) == "success"
    assert sync.evaluate_checks(["lint", "web"], [done, running], []) is None
    assert sync.evaluate_checks(["lint", "web"], [done, failed], []) == "failure"
    # Not reported at all yet is pending, never success.
    assert sync.evaluate_checks(["lint", "web"], [done], []) is None
    # A legacy commit status can satisfy (or fail) a context too.
    assert (
        sync.evaluate_checks(["ci/x"], [], [{"context": "ci/x", "state": "success"}]) == "success"
    )
    assert sync.evaluate_checks(["ci/x"], [], [{"context": "ci/x", "state": "error"}]) == "failure"


def test_wait_for_checks_polls_until_settled_then_times_out() -> None:
    states = iter(
        [
            ([{"name": "lint", "status": "queued", "conclusion": None}], []),
            ([{"name": "lint", "status": "completed", "conclusion": "success"}], []),
        ],
    )
    sleeps: list[float] = []
    with mock.patch.object(sync, "commit_check_state", side_effect=lambda *_a: next(states)):
        outcome = sync.wait_for_checks(
            "o/r",
            "sha",
            ["lint"],
            "x",
            timeout=100,
            interval=5,
            sleep=sleeps.append,
            clock=lambda: 0.0,
        )
    assert outcome == "success"
    assert sleeps == [5]

    ticks = iter([0.0, 50.0, 101.0])
    pending = ([{"name": "lint", "status": "in_progress", "conclusion": None}], [])
    with mock.patch.object(sync, "commit_check_state", return_value=pending):
        outcome = sync.wait_for_checks(
            "o/r",
            "sha",
            ["lint"],
            "x",
            timeout=100,
            interval=5,
            sleep=lambda _s: None,
            clock=lambda: next(ticks),
        )
    assert outcome == "timeout"


# --------------------------------------------------------------------------
# Git plumbing (local bare remote, no network)
# --------------------------------------------------------------------------


def test_build_filtered_tree_excludes_matched_paths(tmp_path: Path) -> None:
    repo, _remote = _make_repo_with_remote(tmp_path)
    _commit(
        repo,
        {"analysis/crates/PREFLIGHT.md": "scan\n"},
        "add excluded path",
    )

    tree_sha = sync.build_filtered_tree(repo, "HEAD")
    names = _git(repo, "ls-tree", "-r", "--name-only", tree_sha).stdout.splitlines()

    assert "analysis/crates/PREFLIGHT.md" not in names
    assert "README.md" in names
    assert ".github/workflows/ci.yml" in names


def test_build_filtered_tree_does_not_touch_working_tree_or_real_index(
    tmp_path: Path,
) -> None:
    repo, _remote = _make_repo_with_remote(tmp_path)
    _commit(repo, {"analysis/crates/PREFLIGHT.md": "scan\n"}, "add excluded path")

    status_before = _git(repo, "status", "--porcelain").stdout
    sync.build_filtered_tree(repo, "HEAD")
    status_after = _git(repo, "status", "--porcelain").stdout

    assert status_before == status_after == ""
    # The excluded file is still on disk and still tracked in the real index —
    # only the throwaway tree omits it.
    assert (repo / "analysis" / "crates" / "PREFLIGHT.md").exists()
    assert "analysis/crates/PREFLIGHT.md" in _git(repo, "ls-files").stdout.splitlines()


def test_no_op_when_filtered_tree_equals_remote_tree(tmp_path: Path) -> None:
    repo, _remote = _make_repo_with_remote(tmp_path)
    # HEAD already equals what's published (no excluded paths present).

    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--remote", "origin", "--dry-run"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "up to date" in result.stdout


def test_dry_run_prints_tree_and_trailer_without_pushing(tmp_path: Path) -> None:
    repo, remote = _make_repo_with_remote(tmp_path)
    head_sha = _commit(repo, {"python/spectrafit_core/fit.py": "# new\n"}, "add file")

    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--remote", "origin", "--dry-run"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DRY RUN" in result.stdout
    assert f"{sync.SYNC_TRAILER}: {head_sha}" in result.stdout
    # Nothing pushed: the bare remote's refs/heads/sync/gitlab must not exist.
    refs = _git(remote, "for-each-ref", "--format=%(refname)").stdout
    assert "refs/heads/sync/gitlab" not in refs


def _build_sync_commit(repo: Path) -> tuple[str, str, str]:
    """(commit sha, parent sha, gitlab head sha) of a freshly built sync commit."""
    parent_sha = _git(repo, "rev-parse", "origin/main").stdout.strip()
    tree_sha = sync.build_filtered_tree(repo, "HEAD")
    head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    subject, body = sync.build_sync_message(head_sha)
    date = sync.commit_date(repo, "HEAD")
    commit_sha = sync.commit_sync_tree(repo, tree_sha, parent_sha, subject, body, date)
    return commit_sha, parent_sha, head_sha


def test_commit_sync_tree_parents_on_remote_and_carries_trailer(tmp_path: Path) -> None:
    repo, _remote = _make_repo_with_remote(tmp_path)
    _commit(repo, {"analysis/crates/PREFLIGHT.md": "scan\n"}, "add excluded path")

    commit_sha, parent_sha, head_sha = _build_sync_commit(repo)

    parents = _git(repo, "log", "-1", "--format=%P", commit_sha).stdout.strip()
    assert parents == parent_sha
    message = _git(repo, "log", "-1", "--format=%B", commit_sha).stdout
    assert sync.parse_sync_trailer(message) == head_sha


def _secret_gitlab_commit(repo: Path) -> str:
    """A GitLab HEAD commit whose author, committer and message must never leak."""
    _write(repo, {"python/spectrafit_core/fit.py": "# new\n"})
    _git(repo, "add", "-A")
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Secret Person",
        "GIT_AUTHOR_EMAIL": "secret@example.org",
        "GIT_COMMITTER_NAME": "Secret Person",
        "GIT_COMMITTER_EMAIL": "secret@example.org",
    }
    _git(repo, "commit", "-q", "-m", "feat: SECRET-MARKER\n\nInternal detail SECRET-BODY.", env=env)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _assert_anonymous(repo: Path, commit_sha: str, gitlab_sha: str) -> None:
    identity = _git(repo, "log", "-1", "--format=%an|%ae|%cn|%ce", commit_sha).stdout.strip()
    assert identity.split("|") == [*_BOT, *_BOT]
    message = _git(repo, "log", "-1", "--format=%B", commit_sha).stdout.strip()
    assert message == f"sync: gitlab main\n\n{sync._SYNC_TEXT}\n\n{sync.SYNC_TRAILER}: {gitlab_sha}"
    # Raw object and the `--format=full` view: no GitLab author, committer,
    # message or developer identity anywhere.
    raw = _git(repo, "cat-file", "-p", commit_sha).stdout
    full = _git(repo, "log", "-1", "--format=full", commit_sha).stdout
    for leak in ("Secret Person", "secret@example.org", "SECRET", "Leaky Dev", "leaky@example.org"):
        assert leak not in raw, leak
        assert leak not in full, leak


def test_commit_sync_tree_is_anonymous_whatever_the_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo, _remote = _make_repo_with_remote(tmp_path)
    gitlab_sha = _secret_gitlab_commit(repo)
    # A developer or runner identity in the environment must not reach the commit.
    for key, value in {
        "GIT_AUTHOR_NAME": "Leaky Dev",
        "GIT_AUTHOR_EMAIL": "leaky@example.org",
        "GIT_COMMITTER_NAME": "Leaky Dev",
        "GIT_COMMITTER_EMAIL": "leaky@example.org",
        "GIT_AUTHOR_DATE": "2001-01-01T00:00:00Z",
    }.items():
        monkeypatch.setenv(key, value)

    commit_sha, _parent, head_sha = _build_sync_commit(repo)

    assert head_sha == gitlab_sha
    _assert_anonymous(repo, commit_sha, gitlab_sha)
    dates = _git(repo, "log", "-1", "--format=%aI|%cI", commit_sha).stdout.strip().split("|")
    assert dates == [sync.commit_date(repo, gitlab_sha)] * 2


def test_commit_sync_tree_is_reproducible(tmp_path: Path) -> None:
    repo, _remote = _make_repo_with_remote(tmp_path)
    _commit(repo, {"python/spectrafit_core/fit.py": "# new\n"}, "add file")

    first, _p1, _h1 = _build_sync_commit(repo)
    second, _p2, _h2 = _build_sync_commit(repo)

    # Same tree, parent and GitLab SHA -> same commit SHA, so a rerun after a
    # check timeout resumes on the commit CI already ran against.
    assert first == second


def test_push_sync_branch_pushes_to_the_bare_remote(tmp_path: Path) -> None:
    repo, remote = _make_repo_with_remote(tmp_path)
    _commit(repo, {"analysis/crates/PREFLIGHT.md": "scan\n"}, "add excluded path")

    commit_sha, _parent, _head = _build_sync_commit(repo)

    # A bare local remote accepts a plain push with no auth needed (in CI the
    # push remote is the deploy-key SSH remote), so this proves the mechanics.
    sync.push_sync_branch(repo, "origin", commit_sha, "sync/gitlab")

    pushed_sha = _git(remote, "rev-parse", "refs/heads/sync/gitlab").stdout.strip()
    assert pushed_sha == commit_sha


def _race_remote_main(tmp_path: Path, remote: Path) -> str:
    """Advance the bare remote's main from a second clone (a contribution merged meanwhile)."""
    other = tmp_path / "other"
    # -b main: same independence from init.defaultBranch as _make_repo_with_remote
    # above — a plain `clone` without it checks out whatever HEAD the remote
    # happens to have, and the push below assumes it is "main".
    _git(tmp_path, "clone", "-q", "-b", "main", str(remote), str(other))
    _git(other, "config", "user.email", "other@example.invalid")
    _git(other, "config", "user.name", "Other")
    sha = _commit(other, {"CONTRIBUTING.md": "hi\n"}, "docs: outside contribution")
    _git(other, "push", "-q", "origin", "main")
    return sha


def test_land_fast_forward_refuses_a_non_fast_forward(tmp_path: Path) -> None:
    repo, remote = _make_repo_with_remote(tmp_path)
    _commit(repo, {"python/spectrafit_core/fit.py": "# new\n"}, "add file")
    commit_sha, _parent, _head = _build_sync_commit(repo)
    racing_sha = _race_remote_main(tmp_path, remote)

    with pytest.raises(subprocess.CalledProcessError):
        sync.land_fast_forward(repo, "origin", commit_sha, "main")
    assert _git(remote, "rev-parse", "refs/heads/main").stdout.strip() == racing_sha


# --------------------------------------------------------------------------
# GitHub REST — network mocked out entirely.
# --------------------------------------------------------------------------


def test_sync_pr_creates_when_no_open_pr_exists() -> None:
    created = {"number": 42, "node_id": "PR_kwID", "html_url": "https://example.invalid/42"}
    with (
        mock.patch.object(sync, "find_open_sync_pr", return_value=None) as find_mock,
        mock.patch.object(sync, "create_sync_pr", return_value=created) as create_mock,
        mock.patch.object(sync, "update_sync_pr") as update_mock,
    ):
        pr = sync.sync_pr(
            "Anselmoo/SpectraFit-Core",
            "sync/gitlab",
            "main",
            "sync: gitlab main",
            "GitLab-Commit: " + "a" * 40,
            token="x",
        )
    assert pr == created
    find_mock.assert_called_once()
    create_mock.assert_called_once()
    update_mock.assert_not_called()


def test_sync_pr_updates_when_an_open_pr_already_exists() -> None:
    existing = {"number": 7, "node_id": "PR_old", "html_url": "https://example.invalid/7"}
    updated = {"number": 7, "node_id": "PR_old", "html_url": "https://example.invalid/7"}
    with (
        mock.patch.object(sync, "find_open_sync_pr", return_value=existing),
        mock.patch.object(sync, "create_sync_pr") as create_mock,
        mock.patch.object(sync, "update_sync_pr", return_value=updated) as update_mock,
    ):
        pr = sync.sync_pr(
            "Anselmoo/SpectraFit-Core",
            "sync/gitlab",
            "main",
            "sync: gitlab main",
            "GitLab-Commit: " + "b" * 40,
            token="x",
        )
    assert pr == updated
    create_mock.assert_not_called()
    update_mock.assert_called_once()


def test_no_github_merge_api_is_used_anywhere() -> None:
    """Landing is a fast-forward push; a GitHub (squash) merge would re-author the commit."""
    source = _SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("enablePullRequestAutoMerge", "mergePullRequest", "/merge", '"SQUASH"'):
        assert forbidden not in source, forbidden


def test_find_open_sync_pr_returns_none_for_empty_list() -> None:
    with mock.patch.object(sync, "_api_request", return_value=(200, [])):
        assert sync.find_open_sync_pr("o/r", "o", "sync/gitlab", "main", token="x") is None


def test_find_open_sync_pr_raises_sync_error_on_bad_status() -> None:
    with mock.patch.object(sync, "_api_request", return_value=(500, {"message": "boom"})):
        try:
            sync.find_open_sync_pr("o/r", "o", "sync/gitlab", "main", token="x")
        except sync.SyncError as exc:
            assert "500" in str(exc)
        else:
            raise AssertionError("expected SyncError")


# --------------------------------------------------------------------------
# CLI: --no-pr skips PR create/update and the landing entirely.
# --------------------------------------------------------------------------


def test_no_pr_flag_pushes_but_skips_pr(tmp_path: Path, monkeypatch) -> None:
    repo, remote = _make_repo_with_remote(tmp_path)
    _commit(
        repo,
        {
            "analysis/crates/PREFLIGHT.md": "scan\n",
            "python/spectrafit_core/fit.py": "# new\n",
        },
        "add excluded path and a real change",
    )
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token-for-local-bare-remote")

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--remote",
            "origin",
            "--push-remote",
            "origin",
            "--no-pr",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--no-pr set" in result.stdout
    refs = _git(remote, "for-each-ref", "--format=%(refname)").stdout
    assert "refs/heads/sync/gitlab" in refs


# --------------------------------------------------------------------------
# main(): the whole forward path against a local bare "mirror" — PR API and
# check polling mocked, git push/fetch real. The push remote is the same bare
# repo (in CI it is the deploy-key SSH remote to the same GitHub repository).
# --------------------------------------------------------------------------


def _run_main(repo: Path, monkeypatch, *extra: str) -> int:
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token-for-local-bare-remote")
    return sync.main(["--remote", "origin", "--push-remote", "origin", *extra])


def test_main_lands_the_anonymous_commit_by_fast_forward_after_green_checks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo, remote = _make_repo_with_remote(tmp_path)
    old_main = _git(remote, "rev-parse", "refs/heads/main").stdout.strip()
    gitlab_sha = _secret_gitlab_commit(repo)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Leaky Dev")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "leaky@example.org")

    with (
        mock.patch.object(sync, "sync_pr", return_value={"number": 1}) as pr_mock,
        mock.patch.object(sync, "required_checks", return_value=["lint"]),
        mock.patch.object(sync, "wait_for_checks", return_value="success") as wait_mock,
    ):
        rc = _run_main(repo, monkeypatch)

    assert rc == 0
    landed = _git(remote, "rev-parse", "refs/heads/main").stdout.strip()
    synced = _git(remote, "rev-parse", "refs/heads/sync/gitlab").stdout.strip()
    # The exact commit CI checked is what lands — no merge, no rewrite.
    assert landed == synced
    assert wait_mock.call_args.args[1] == landed
    assert _git(remote, "rev-parse", f"{landed}^").stdout.strip() == old_main
    _assert_anonymous(remote, landed, gitlab_sha)
    # The PR title/body carry the same fixed subject and trailer, nothing more.
    _repo, _branch, _base, subject, body, _token = pr_mock.call_args.args
    assert subject == "sync: gitlab main"
    assert "SECRET" not in body

    # A second run with nothing new on GitLab is a clean no-op: no PR at all.
    with mock.patch.object(sync, "sync_pr") as pr_again:
        assert _run_main(repo, monkeypatch) == 0
    pr_again.assert_not_called()


@pytest.mark.parametrize(
    ("contexts", "outcome", "expected_rc"),
    [
        (["lint"], "failure", 1),
        ([], "success", 1),  # no required check configured -> refuse, never land unguarded
        (["lint"], "timeout", 0),  # leave the PR open; the rerun resumes
    ],
)
def test_main_does_not_land_without_green_required_checks(
    tmp_path: Path,
    monkeypatch,
    contexts: list[str],
    outcome: str,
    expected_rc: int,
) -> None:
    repo, remote = _make_repo_with_remote(tmp_path)
    old_main = _git(remote, "rev-parse", "refs/heads/main").stdout.strip()
    _commit(repo, {"python/spectrafit_core/fit.py": "# new\n"}, "add file")

    with (
        mock.patch.object(sync, "sync_pr", return_value={"number": 1}),
        mock.patch.object(sync, "required_checks", return_value=contexts),
        mock.patch.object(sync, "wait_for_checks", return_value=outcome),
    ):
        rc = _run_main(repo, monkeypatch)

    assert rc == expected_rc
    assert _git(remote, "rev-parse", "refs/heads/main").stdout.strip() == old_main


def test_main_aborts_when_main_moved_while_checks_ran(tmp_path: Path, monkeypatch) -> None:
    repo, remote = _make_repo_with_remote(tmp_path)
    _commit(repo, {"python/spectrafit_core/fit.py": "# new\n"}, "add file")
    racing: list[str] = []

    def _race_then_succeed(*_args, **_kwargs) -> str:
        racing.append(_race_remote_main(tmp_path, remote))
        return "success"

    with (
        mock.patch.object(sync, "sync_pr", return_value={"number": 1}),
        mock.patch.object(sync, "required_checks", return_value=["lint"]),
        mock.patch.object(sync, "wait_for_checks", side_effect=_race_then_succeed),
    ):
        rc = _run_main(repo, monkeypatch)

    assert rc == 1
    # The contribution that landed meanwhile is untouched — never force-pushed over.
    assert _git(remote, "rev-parse", "refs/heads/main").stdout.strip() == racing[0]


def test_bot_identity_is_one_github_app_bot_everywhere() -> None:
    """Sync, snapshot and backport commit as the same GitHub App bot account.

    A ``<id>+<slug>[bot]@users.noreply.github.com`` address makes GitHub
    attribute the commit to the App's bot user instead of showing an
    unverified, unlinked e-mail (which the main ruleset treats as an
    unattributed change). All three writers must agree on it.
    """
    import re

    root = Path(__file__).resolve().parents[2]
    name, email = _BOT
    assert re.fullmatch(r"\d+\+[a-z0-9-]+\[bot\]@users\.noreply\.github\.com", email), email
    assert email.split("+", 1)[1].startswith(name.removesuffix("[bot]")), (name, email)
    for rel in ("scripts/publish_snapshot.sh", ".gitlab/75-backport.yml"):
        text = (root / rel).read_text()
        assert f'git config user.email "{email}"' in text, rel
        assert f'git config user.name "{name}"' in text, rel


# --------------------------------------------------------------------------
# sync_guard: never roll GitHub back, never sync over un-backported work.
# --------------------------------------------------------------------------


def _push_to_remote(tmp_path: Path, remote: Path, files: dict[str, str], message: str) -> str:
    """Commit on the mirror's main from a throwaway clone (GitHub-side work)."""
    clone = tmp_path / f"clone-{len(list(tmp_path.glob('clone-*')))}"
    _git(tmp_path, "clone", "-q", str(remote), str(clone))
    _git(clone, "config", "user.email", "contrib@example.org")
    _git(clone, "config", "user.name", "Contributor")
    sha = _commit(clone, files, message)
    _git(clone, "push", "-q", "origin", "HEAD:main")
    return sha


def _sync_boundary_on_remote(
    tmp_path: Path,
    remote: Path,
    files: dict[str, str],
    gitlab_sha: str,
) -> str:
    return _push_to_remote(
        tmp_path,
        remote,
        files,
        f"sync: gitlab main\n\nGitLab-Commit: {gitlab_sha}",
    )


def test_stale_pipeline_does_not_roll_github_back(tmp_path: Path, monkeypatch, capsys) -> None:
    repo, remote = _make_repo_with_remote(tmp_path)
    older = _commit(repo, {"a.txt": "2\n"}, "g2")
    newer = _commit(repo, {"a.txt": "3\n"}, "g3")
    _sync_boundary_on_remote(tmp_path, remote, {"a.txt": "3\n"}, newer)
    _git(repo, "checkout", "-q", "--detach", older)  # the late, older pipeline

    assert _run_main(repo, monkeypatch, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "stale" in out
    assert "DRY RUN" not in out
    assert "refs/heads/sync/gitlab" not in _git(remote, "for-each-ref").stdout


def test_sync_refuses_while_github_work_is_not_backported(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    repo, remote = _make_repo_with_remote(tmp_path)
    synced = _commit(repo, {"a.txt": "2\n"}, "g2")
    _sync_boundary_on_remote(tmp_path, remote, {"a.txt": "2\n"}, synced)
    contribution = _push_to_remote(
        tmp_path,
        remote,
        {"docs.md": "contributed\n"},
        "docs: contribution",
    )
    _commit(repo, {"b.txt": "gitlab-only\n"}, "g3")  # GitLab moved on without it

    assert _run_main(repo, monkeypatch, "--dry-run") == 1
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "backport:github" in out
    assert f"{contribution[:10]} docs: contribution" in out
    assert "refs/heads/sync/gitlab" not in _git(remote, "for-each-ref").stdout

    # Once backport:github has landed it on GitLab, the sync goes ahead.
    _git(repo, "fetch", "-q", "origin", "main")
    _git(repo, "cherry-pick", "-x", contribution)
    assert _run_main(repo, monkeypatch, "--dry-run") == 0
    assert "REFUSED" not in capsys.readouterr().out


def test_sync_pr_is_opened_as_a_draft() -> None:
    """A draft PR has no merge button: nobody can squash (re-author) the sync."""
    with mock.patch.object(sync, "_api_request", return_value=(201, {"number": 9})) as api:
        sync.create_sync_pr("o/r", "sync/gitlab", "main", "sync: gitlab main", "body", "t")
    assert api.call_args.kwargs["payload"]["draft"] is True
