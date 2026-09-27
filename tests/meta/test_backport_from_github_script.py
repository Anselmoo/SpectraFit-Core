"""Structural + logic checks for scripts/backport_from_github.py.

Git plumbing (`find_sync_boundary`, `candidates_after_boundary`,
`candidates_on_feature_branch`, `cherry_pick_onto_branch`) is exercised
against real throwaway git repos — no network needed. The GitLab REST API
calls (`open_backport_mr_exists`, `open_merge_request`) are exercised through
`run_open_mr` with `backport_from_github._http_request` monkeypatched — no
real HTTP.

`scripts/publish_sync.py` (SYNC_TRAILER / parse_sync_trailer) is being
written concurrently by another agent under the same shared-design task. If
it isn't there yet, a minimal stub standing in for its documented contract is
written to a throwaway directory and prepended to `sys.path` ahead of
`scripts/` — never as `scripts/publish_sync.py` itself.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

if not (_SCRIPTS_DIR / "publish_sync.py").exists():
    _stub_dir = Path(tempfile.mkdtemp(prefix="publish_sync_stub_"))
    (_stub_dir / "publish_sync.py").write_text(
        '"""Test-only stand-in for scripts/publish_sync.py (written concurrently\n'
        "by another agent under the same shared-design task) until it lands.\n"
        "Mirrors its documented contract exactly: SYNC_TRAILER + parse_sync_trailer.\n"
        '"""\n'
        "from __future__ import annotations\n\n"
        'SYNC_TRAILER = "GitLab-Commit"\n\n\n'
        "def parse_sync_trailer(message: str) -> str | None:\n"
        '    """Return the trailer\'s SHA, or None if `message` carries none."""\n'
        '    prefix = f"{SYNC_TRAILER}: "\n'
        "    for line in message.splitlines():\n"
        "        stripped = line.strip()\n"
        "        if stripped.startswith(prefix):\n"
        "            return stripped[len(prefix) :].strip()\n"
        "    return None\n",
    )
    # Ahead of _SCRIPTS_DIR so a same-named real module never shadows it, and
    # the reverse: once the real file lands, delete this stub path from
    # sys.path (a fresh process picks up the real one automatically anyway).
    sys.path.insert(0, str(_stub_dir))

import backport_from_github as backport  # ty: ignore[unresolved-import]

_SCRIPT = _SCRIPTS_DIR / "backport_from_github.py"
_FAKE_SHA = "0" * 40


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


def _commit(
    repo: Path,
    filename: str,
    content: str,
    message: str,
    author: tuple[str, str, str] | None = None,
) -> str:
    """Commit `filename`; `author` = (name, email, ISO date) for a distinct author."""
    (repo / filename).write_text(content)
    _git(repo, "add", filename)
    env = None
    if author is not None:
        name, email, date = author
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_AUTHOR_DATE": date,
        }
    _git(repo, "commit", "-q", "-m", message, env=env)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


# Distinct GitHub-side authors: the backport must carry each one over verbatim.
_DEPENDABOT = (
    "dependabot[bot]",
    "49699333+dependabot[bot]@users.noreply.github.com",
    "2026-01-02T03:04:05+02:00",
)
_OUTSIDER = ("Outside Contributor", "outside@example.org", "2026-02-03T04:05:06+01:00")


def _author_of(repo: Path, rev: str) -> tuple[str, str, str]:
    name, email, date = (
        _git(repo, "log", "-1", "--format=%an|%ae|%aI", rev).stdout.strip().split("|")
    )
    return name, email, date


def test_script_exists() -> None:
    assert _SCRIPT.exists()


# ---------------------------------------------------------------------------
# Boundary detection + candidate selection (main/boundary mode)
# ---------------------------------------------------------------------------


def _make_boundary_repo(tmp_path: Path) -> Path:
    """github/main: orphan-snapshot root (trailer) -> two GitHub-native commits."""
    repo = tmp_path / "github_main"
    _init_repo(repo)
    _commit(
        repo,
        "f.txt",
        "one\n",
        f"Initial commit\n\nGitLab-Commit: {_FAKE_SHA}",
    )
    _commit(repo, "f.txt", "two\n", "chore(deps): bump numpy (dependabot)")
    _commit(repo, "f.txt", "three\n", "fix: outside PR merged straight to main")
    return repo


def test_find_sync_boundary_and_candidates_after_it(tmp_path: Path) -> None:
    repo = _make_boundary_repo(tmp_path)
    ci_checkout = tmp_path / "ci_checkout"
    _init_repo(ci_checkout)
    _commit(ci_checkout, "g.txt", "base\n", "ci checkout base")
    _git(ci_checkout, "remote", "add", "github", str(repo))
    _git(ci_checkout, "fetch", "github", "main")

    import os

    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        boundary = backport.find_sync_boundary("github/main")
        assert boundary is not None
        message = backport.commit_message(boundary)
        assert backport.parse_sync_trailer(message) == _FAKE_SHA

        candidates = backport.candidates_after_boundary("github/main", boundary)
    finally:
        os.chdir(old_cwd)

    assert [subject for _sha, subject in candidates] == [
        "chore(deps): bump numpy (dependabot)",
        "fix: outside PR merged straight to main",
    ]
    assert all(len(sha) == 40 for sha, _subject in candidates)


def test_no_boundary_returns_none_not_everything(tmp_path: Path) -> None:
    """A github/main with no trailer commit at all — the pre-sync-tooling
    state — must report "no boundary", never silently list every commit."""
    repo = tmp_path / "github_main_no_trailer"
    _init_repo(repo)
    _commit(repo, "f.txt", "one\n", "plain commit, no trailer")
    _commit(repo, "f.txt", "two\n", "another plain commit")

    ci_checkout = tmp_path / "ci_checkout"
    _init_repo(ci_checkout)
    _commit(ci_checkout, "g.txt", "base\n", "ci checkout base")
    _git(ci_checkout, "remote", "add", "github", str(repo))
    _git(ci_checkout, "fetch", "github", "main")

    import os

    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        assert backport.find_sync_boundary("github/main") is None
    finally:
        os.chdir(old_cwd)


def test_main_refuses_without_boundary_and_exits_nonzero(tmp_path: Path) -> None:
    repo = tmp_path / "github_main_no_trailer"
    _init_repo(repo)
    _commit(repo, "f.txt", "one\n", "plain commit, no trailer")
    _commit(repo, "f.txt", "two\n", "another plain commit")

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--remote-name",
            "self",
            "--remote-url",
            str(repo),
            "--github-branch",
            "main",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "refusing" in result.stdout.lower()
    assert "trailer" in result.stdout.lower()
    # And it must NOT have listed the two plain commits as if they were candidates.
    assert "plain commit" not in result.stdout


def test_main_boundary_mode_lists_candidates_with_cherry_pick_recipe(
    tmp_path: Path,
) -> None:
    repo = _make_boundary_repo(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--remote-name",
            "self",
            "--remote-url",
            str(repo),
            "--github-branch",
            "main",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "2 commit(s)" in result.stdout
    assert "chore(deps): bump numpy (dependabot)" in result.stdout
    assert "fix: outside PR merged straight to main" in result.stdout
    assert "git cherry-pick" in result.stdout


def test_main_boundary_mode_no_candidates_is_clean_noop(tmp_path: Path) -> None:
    repo = tmp_path / "github_main_clean"
    _init_repo(repo)
    _commit(repo, "f.txt", "one\n", f"Initial commit\n\nGitLab-Commit: {_FAKE_SHA}")

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--remote-name",
            "self",
            "--remote-url",
            str(repo),
            "--github-branch",
            "main",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "pending backport" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Feature-branch mode: base is the merge-base with github/main, not local main
# ---------------------------------------------------------------------------


def _make_repo_with_feature_branch_off_github_main(
    tmp_path: Path,
) -> tuple[Path, str]:
    """github/main carries its OWN unrelated orphan history (like the real
    mirror). The feature branch forks from github/main, not from any local
    ref — exercising that the merge-base is computed against github/main."""
    repo = tmp_path / "github_repo"
    _init_repo(repo)
    _commit(repo, "f.txt", "one\n", f"Initial commit\n\nGitLab-Commit: {_FAKE_SHA}")
    _git(repo, "checkout", "-q", "-b", "feature/widget")
    _commit(repo, "f.txt", "two\n", "widget: first pass")
    _commit(repo, "f.txt", "three\n", "widget: fix typo")
    _git(repo, "checkout", "-q", "main")
    return repo, "feature/widget"


def test_main_backports_a_named_branch_via_merge_base_with_github_main(
    tmp_path: Path,
) -> None:
    repo, feature_branch = _make_repo_with_feature_branch_off_github_main(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--remote-name",
            "self",
            "--remote-url",
            str(repo),
            "--github-branch",
            feature_branch,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert f"self/{feature_branch}" in result.stdout
    assert "2 commit(s)" in result.stdout
    assert "widget: first pass" in result.stdout
    assert "widget: fix typo" in result.stdout
    assert "git cherry-pick" in result.stdout


def test_main_squash_flag_suggests_squash_merge_not_cherry_pick(
    tmp_path: Path,
) -> None:
    repo, feature_branch = _make_repo_with_feature_branch_off_github_main(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--remote-name",
            "self",
            "--remote-url",
            str(repo),
            "--github-branch",
            feature_branch,
            "--squash",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert f"git merge --squash self/{feature_branch}" in result.stdout
    assert "git cherry-pick" not in result.stdout


def test_squash_and_open_mr_are_mutually_exclusive(tmp_path: Path) -> None:
    repo = tmp_path / "github_main_clean"
    _init_repo(repo)
    _commit(repo, "f.txt", "one\n", f"Initial commit\n\nGitLab-Commit: {_FAKE_SHA}")

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--remote-url",
            str(repo),
            "--squash",
            "--open-mr",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "mutually exclusive" in (result.stderr + result.stdout).lower()


# ---------------------------------------------------------------------------
# --open-mr: cherry-pick onto a fresh branch, push, open the MR (HTTP mocked)
# ---------------------------------------------------------------------------


def _make_open_mr_fixture(tmp_path: Path) -> tuple[Path, Path, list[tuple[str, str]]]:
    """Returns (ci_checkout, gitlab_bare, candidates) with `github` and
    `gitlab` remotes already configured and `github/main` already fetched,
    cwd NOT changed (caller chdir's)."""
    github_repo = tmp_path / "github_repo"
    _init_repo(github_repo)
    _commit(github_repo, "f.txt", "one\n", f"Initial commit\n\nGitLab-Commit: {_FAKE_SHA}")
    _commit(
        github_repo,
        "f.txt",
        "two\n",
        "chore(deps): bump numpy (dependabot)",
        author=_DEPENDABOT,
    )
    _commit(
        github_repo,
        "f.txt",
        "three\n",
        "fix: outside PR\n\nLonger explanation from the contributor.",
        author=_OUTSIDER,
    )

    gitlab_seed = tmp_path / "gitlab_seed"
    _init_repo(gitlab_seed)
    # Same tree as github_repo's trailer commit (a real snapshot publish is a
    # clone of gitlab's tree at that point) so the later cherry-picks' diffs
    # have matching context to apply onto cleanly.
    _commit(gitlab_seed, "f.txt", "one\n", "gitlab base commit")
    gitlab_bare = tmp_path / "gitlab.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(gitlab_bare))
    _git(gitlab_seed, "remote", "add", "origin", str(gitlab_bare))
    _git(gitlab_seed, "push", "-q", "origin", "main")

    ci_checkout = tmp_path / "ci_checkout"
    _init_repo(ci_checkout)
    _commit(ci_checkout, "h.txt", "ci base\n", "ci checkout base")
    _git(ci_checkout, "remote", "add", "github", str(github_repo))
    _git(ci_checkout, "remote", "add", "gitlab", str(gitlab_bare))
    _git(ci_checkout, "fetch", "github", "main")

    import os

    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        boundary = backport.find_sync_boundary("github/main")
        assert boundary is not None
        candidates = backport.candidates_after_boundary("github/main", boundary)
    finally:
        os.chdir(old_cwd)
    assert len(candidates) == 2
    return ci_checkout, gitlab_bare, candidates


class _FakeHttp:
    """Records every call and answers like the GitLab API.

    GET on the MR list returns `.get_result`, GET on one MR returns
    `.mr_result` (its `head_pipeline`), POST on `/pipelines` returns
    `.pipeline_result`, any other POST (the MR itself) returns `.post_result`.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []
        self.get_result: list[dict[str, object]] = []
        self.post_result: dict[str, object] = {"web_url": "https://gitlab.example/mr/1", "iid": 1}
        self.mr_result: dict[str, object] = {
            "iid": 1,
            "head_pipeline": {
                "id": 77,
                "status": "created",
                "web_url": "https://gitlab.example/p/77",
            },
        }
        self.pipeline_result: dict[str, object] = {
            "id": 88,
            "status": "created",
            "web_url": "https://gitlab.example/p/88",
        }

    def __call__(
        self,
        url: str,
        token: str,
        method: str = "GET",
        data: dict[str, object] | None = None,
    ) -> object:
        self.calls.append((method, url, data))
        assert token == "test-backport-token"
        if method == "GET":
            return (
                self.mr_result if url.rstrip("/").endswith("/merge_requests/1") else self.get_result
            )
        if url.endswith("/pipelines"):
            return self.pipeline_result
        return self.post_result


def test_run_open_mr_cherry_picks_pushes_and_opens_mr(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ci_checkout, gitlab_bare, candidates = _make_open_mr_fixture(tmp_path)
    fake_http = _FakeHttp()
    monkeypatch.setattr(backport, "_http_request", fake_http)
    monkeypatch.setenv("BACKPORT_TOKEN", "test-backport-token")

    import argparse
    import os

    args = argparse.Namespace(
        gitlab_remote_name="gitlab",
        gitlab_remote_url=None,
        target_branch="main",
        mr_host="https://gitlab.example",
        mr_project="anhahn/spectrafit-core",
    )

    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        rc = backport.run_open_mr(args, "github/main", candidates)
    finally:
        os.chdir(old_cwd)

    assert rc == 0
    methods = [call[0] for call in fake_http.calls]
    # list open MRs, create the MR, read its head pipeline (GitLab made one).
    assert methods == ["GET", "POST", "GET"]

    get_url = fake_http.calls[0][1]
    assert "state=opened" in get_url
    assert "anhahn%2Fspectrafit-core" in get_url or "anhahn/spectrafit-core" in get_url

    _post_method, post_url, post_data = fake_http.calls[1]
    assert post_url.endswith("/merge_requests")
    assert post_data is not None
    branch_name = str(post_data["source_branch"])
    assert branch_name.startswith(backport.BACKPORT_BRANCH_PREFIX)
    assert post_data["target_branch"] == "main"
    assert "chore(deps): bump numpy" in str(post_data["description"])
    assert "fix: outside PR" in str(post_data["description"])
    pushed = _git(gitlab_bare, "log", branch_name, "--pretty=format:%s").stdout.splitlines()
    assert pushed[0] == "fix: outside PR"  # newest cherry-pick first in git log
    assert pushed[1] == "chore(deps): bump numpy (dependabot)"
    assert pushed[2] == "gitlab base commit"

    # -x leaves a "(cherry picked from commit ...)" trailer.
    full_message = _git(gitlab_bare, "log", "-1", "--format=%B", branch_name).stdout
    assert "(cherry picked from commit" in full_message

    # The GitLab MR must not squash on merge — history is the point of this
    # direction.
    assert post_data["squash"] is False


def test_run_open_mr_keeps_every_commit_with_its_original_author_date_and_message(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """GitHub -> GitLab carries history: one GitLab commit per GitHub commit,
    author name/email/date and message verbatim plus the `-x` line — no
    squash, no re-attribution to the CI identity that ran the cherry-pick."""
    ci_checkout, gitlab_bare, candidates = _make_open_mr_fixture(tmp_path)
    monkeypatch.setattr(backport, "_http_request", _FakeHttp())
    monkeypatch.setenv("BACKPORT_TOKEN", "test-backport-token")

    import argparse

    args = argparse.Namespace(
        gitlab_remote_name="gitlab",
        gitlab_remote_url=None,
        target_branch="main",
        mr_host="https://gitlab.example",
        mr_project="anhahn/spectrafit-core",
    )
    monkeypatch.chdir(ci_checkout)
    assert backport.run_open_mr(args, "github/main", candidates) == 0

    branch_name = next(
        line.split("refs/heads/", 1)[1]
        for line in _git(gitlab_bare, "for-each-ref", "--format=%(refname)").stdout.splitlines()
        if line.startswith(f"refs/heads/{backport.BACKPORT_BRANCH_PREFIX}")
    )
    picked = _git(gitlab_bare, "rev-list", "--reverse", f"main..{branch_name}").stdout.split()
    assert len(picked) == len(candidates) == 2  # one commit each — nothing squashed

    for (original_sha, _subject), picked_sha, author in zip(
        candidates,
        picked,
        (_DEPENDABOT, _OUTSIDER),
        strict=True,
    ):
        assert _author_of(ci_checkout, original_sha) == author
        assert _author_of(gitlab_bare, picked_sha) == author
        original_message = _git(
            ci_checkout,
            "log",
            "-1",
            "--format=%B",
            original_sha,
        ).stdout.strip()
        picked_message = _git(gitlab_bare, "log", "-1", "--format=%B", picked_sha).stdout.strip()
        assert picked_message == f"{original_message}\n\n(cherry picked from commit {original_sha})"


def test_run_open_mr_skips_when_open_backport_mr_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ci_checkout, gitlab_bare, candidates = _make_open_mr_fixture(tmp_path)
    fake_http = _FakeHttp()
    fake_http.get_result = [
        {"source_branch": "backport/github-20260101", "iid": 7},
    ]
    monkeypatch.setattr(backport, "_http_request", fake_http)
    monkeypatch.setenv("BACKPORT_TOKEN", "test-backport-token")

    import argparse
    import os

    args = argparse.Namespace(
        gitlab_remote_name="gitlab",
        gitlab_remote_url=None,
        target_branch="main",
        mr_host="https://gitlab.example",
        mr_project="anhahn/spectrafit-core",
    )

    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        rc = backport.run_open_mr(args, "github/main", candidates)
    finally:
        os.chdir(old_cwd)

    assert rc == 0
    assert [call[0] for call in fake_http.calls] == ["GET"]  # no POST — skipped
    # Nothing pushed: gitlab.git's main is still exactly the seeded commit.
    branches = _git(gitlab_bare, "branch", "--list").stdout
    assert "backport/github-" not in branches


def test_run_open_mr_requires_backport_token(tmp_path: Path, monkeypatch) -> None:
    ci_checkout, _gitlab_bare, candidates = _make_open_mr_fixture(tmp_path)
    monkeypatch.delenv("BACKPORT_TOKEN", raising=False)

    import argparse
    import os

    args = argparse.Namespace(
        gitlab_remote_name="gitlab",
        gitlab_remote_url=None,
        target_branch="main",
        mr_host="https://gitlab.example",
        mr_project="anhahn/spectrafit-core",
    )

    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        rc = backport.run_open_mr(args, "github/main", candidates)
    finally:
        os.chdir(old_cwd)

    assert rc == 1


# ---------------------------------------------------------------------------
# Conflict path: cherry-pick aborts, no auto-resolve, non-zero return
# ---------------------------------------------------------------------------


def test_cherry_pick_onto_branch_conflict_aborts_and_reports_failing_sha(
    tmp_path: Path,
) -> None:
    # base branch and the "github" candidate both edit the same line of the
    # same file differently -> guaranteed conflict on cherry-pick.
    base_repo = tmp_path / "base_repo"
    _init_repo(base_repo)
    _commit(base_repo, "f.txt", "base\n", "base commit")
    _commit(base_repo, "f.txt", "base changed on gitlab\n", "gitlab-side edit")
    base_sha = _git(base_repo, "rev-parse", "HEAD").stdout.strip()

    conflicting_repo = tmp_path / "conflicting_repo"
    _init_repo(conflicting_repo)
    _commit(conflicting_repo, "f.txt", "base\n", "base commit")
    conflicting_sha = _commit(
        conflicting_repo,
        "f.txt",
        "base changed on github\n",
        "github-side edit",
    )

    ci_checkout = tmp_path / "ci_checkout"
    _init_repo(ci_checkout)
    _commit(ci_checkout, "h.txt", "ci base\n", "ci checkout base")
    _git(ci_checkout, "remote", "add", "base", str(base_repo))
    _git(ci_checkout, "remote", "add", "conflicting", str(conflicting_repo))
    _git(ci_checkout, "fetch", "base", "main")
    _git(ci_checkout, "fetch", "conflicting", "main")

    import os

    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        failing_sha = backport.cherry_pick_onto_branch(
            "backport/github-conflict-test",
            "base/main",
            [(conflicting_sha, "github-side edit")],
        )
        assert failing_sha == conflicting_sha
        # No leftover in-progress cherry-pick.
        assert not (ci_checkout / ".git" / "CHERRY_PICK_HEAD").exists()
        # Branch was created (from base_sha) but nothing conflicting landed on it.
        head_message = _git(ci_checkout, "log", "-1", "--format=%s").stdout.strip()
        assert head_message == "gitlab-side edit"
    finally:
        os.chdir(old_cwd)
    assert base_sha  # base_sha computed only to document the fixture's shape


# ---------------------------------------------------------------------------
# Merge candidates: a GitHub PR merged with "Create a merge commit" is expanded
# into its own commits, each backported individually (history-preserving
# direction). `-m 1` survives only as the fallback for a merge that reaches
# cherry_pick_onto_branch anyway.
# ---------------------------------------------------------------------------


def test_candidates_after_boundary_expands_a_merge_into_its_pr_commits(tmp_path: Path) -> None:
    github_repo = tmp_path / "github_repo"
    _init_repo(github_repo)
    boundary = _commit(
        github_repo,
        "f.txt",
        "one\n",
        f"Initial commit\n\nGitLab-Commit: {_FAKE_SHA}",
    )
    _git(github_repo, "checkout", "-q", "-b", "contrib")
    first = _commit(
        github_repo,
        "a.txt",
        "a\n",
        "docs: first contribution commit",
        author=_OUTSIDER,
    )
    _git(github_repo, "checkout", "-q", "main")
    direct = _commit(github_repo, "d.txt", "d\n", "chore(deps): bump uv", author=_DEPENDABOT)
    _git(github_repo, "checkout", "-q", "contrib")
    # "Update branch" merge of main into the PR — must not become a candidate.
    _git(github_repo, "merge", "-q", "--no-ff", "-m", "Merge branch 'main' into contrib", "main")
    second = _commit(
        github_repo,
        "b.txt",
        "b\n",
        "docs: second contribution commit",
        author=_OUTSIDER,
    )
    _git(github_repo, "checkout", "-q", "main")
    merger_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Maintainer Who Merged",
        "GIT_AUTHOR_EMAIL": "merger@example.org",
    }
    _git(
        github_repo,
        "merge",
        "--no-ff",
        "-m",
        "Merge pull request #3 from outsider/contrib",
        "contrib",
        env=merger_env,
    )
    merge_sha = _git(github_repo, "rev-parse", "HEAD").stdout.strip()

    old_cwd = Path.cwd()
    os.chdir(github_repo)
    try:
        assert backport.expand_merge(merge_sha) == [first, second]
        assert backport.expand_merge(direct) == [direct]
        candidates = backport.candidates_after_boundary("main", boundary)
    finally:
        os.chdir(old_cwd)

    # First-parent order, the merge replaced by its PR commits (oldest first);
    # neither the merge commit nor the nested "Update branch" merge remains,
    # so the merger's identity never becomes a backported commit's author.
    assert [sha for sha, _ in candidates] == [direct, first, second]


def test_cherry_pick_onto_branch_backports_expanded_pr_commits_individually(
    tmp_path: Path,
) -> None:
    github_repo = tmp_path / "github_repo"
    _init_repo(github_repo)
    boundary = _commit(
        github_repo,
        "f.txt",
        "base\n",
        f"Initial commit\n\nGitLab-Commit: {_FAKE_SHA}",
    )
    _git(github_repo, "checkout", "-q", "-b", "contrib")
    first = _commit(github_repo, "a.txt", "a\n", "docs: first", author=_OUTSIDER)
    second = _commit(github_repo, "a.txt", "a2\n", "docs: second", author=_DEPENDABOT)
    _git(github_repo, "checkout", "-q", "main")
    _git(github_repo, "merge", "-q", "--no-ff", "-m", "Merge pull request #4", "contrib")

    gitlab_repo = tmp_path / "gitlab_repo"
    _init_repo(gitlab_repo)
    _commit(gitlab_repo, "f.txt", "base\n", "gitlab base commit")

    ci_checkout = tmp_path / "ci_checkout"
    _init_repo(ci_checkout)
    _commit(ci_checkout, "z.txt", "ci\n", "ci checkout base")
    _git(ci_checkout, "remote", "add", "github", str(github_repo))
    _git(ci_checkout, "remote", "add", "gitlab", str(gitlab_repo))
    _git(ci_checkout, "fetch", "-q", "github", "main")
    _git(ci_checkout, "fetch", "-q", "gitlab", "main")

    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        candidates = backport.candidates_after_boundary("github/main", boundary)
        assert [sha for sha, _ in candidates] == [first, second]
        assert (
            backport.cherry_pick_onto_branch("backport/github-x", "gitlab/main", candidates) is None
        )
        picked = _git(ci_checkout, "rev-list", "--reverse", "gitlab/main..HEAD").stdout.split()
    finally:
        os.chdir(old_cwd)

    assert len(picked) == 2
    for original, picked_sha, author in zip(
        (first, second),
        picked,
        (_OUTSIDER, _DEPENDABOT),
        strict=True,
    ):
        assert _author_of(ci_checkout, picked_sha) == author
        message = _git(ci_checkout, "log", "-1", "--format=%B", picked_sha).stdout
        assert f"(cherry picked from commit {original})" in message
    assert (ci_checkout / "a.txt").read_text() == "a2\n"


def test_cherry_pick_onto_branch_replays_merge_commit_with_dash_m_1(
    tmp_path: Path,
) -> None:
    """Fallback: a candidate that is still a merge commit when it reaches
    `cherry_pick_onto_branch` (feature-branch mode, or a PR with no non-merge
    commit — see `expand_merge`) is replayed with `-m 1` against its first
    parent — plain `cherry-pick` refuses a merge commit with no `-m` at all."""
    base_repo = tmp_path / "base_repo"
    _init_repo(base_repo)
    _commit(base_repo, "f.txt", "base\n", "base commit")

    source_repo = tmp_path / "source_repo"
    _init_repo(source_repo)
    _commit(source_repo, "h.txt", "base\n", "base commit")
    _git(source_repo, "checkout", "-q", "-b", "feature")
    _commit(source_repo, "widget.txt", "widget\n", "feature: add widget")
    _git(source_repo, "checkout", "-q", "main")
    _commit(source_repo, "h.txt", "changed\n", "main: unrelated change")
    _git(source_repo, "merge", "--no-ff", "-m", "Merge branch 'feature'", "feature")
    merge_sha = _git(source_repo, "rev-parse", "HEAD").stdout.strip()
    parents = _git(source_repo, "rev-list", "--parents", "-n", "1", merge_sha).stdout.split()
    assert (
        len(parents) == 3
    )  # merge_sha itself + 2 parents — confirms the fixture built a real merge

    ci_checkout = tmp_path / "ci_checkout"
    _init_repo(ci_checkout)
    _commit(ci_checkout, "z.txt", "ci base\n", "ci checkout base")
    _git(ci_checkout, "remote", "add", "base", str(base_repo))
    _git(ci_checkout, "remote", "add", "source", str(source_repo))
    _git(ci_checkout, "fetch", "base", "main")
    _git(ci_checkout, "fetch", "source", "main")

    import os

    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        failing_sha = backport.cherry_pick_onto_branch(
            "backport/github-merge-test",
            "base/main",
            [(merge_sha, "Merge branch 'feature'")],
        )
        assert failing_sha is None
        # The whole merged PR diff carried over: the feature branch's own
        # addition landed, base/main's pre-existing file is untouched, and
        # nothing outside the merge's first-parent diff was pulled in.
        assert (ci_checkout / "widget.txt").read_text() == "widget\n"
        assert (ci_checkout / "f.txt").read_text() == "base\n"
        assert not (ci_checkout / "h.txt").exists()
        log_message = _git(ci_checkout, "log", "-1", "--format=%B").stdout
        assert "(cherry picked from commit" in log_message
    finally:
        os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# Boundary freeze: the sync boundary on github/main only advances on a
# GitLab->GitHub sync with differing content, which a backport-only round
# does not itself produce — so a stale boundary re-selects an already-applied
# candidate. filter_already_applied is what drops it before cherry-picking.
# ---------------------------------------------------------------------------


def _make_open_mr_fixture_with_prior_backport(
    tmp_path: Path,
) -> tuple[Path, Path, list[tuple[str, str]], str]:
    """Like `_make_open_mr_fixture`, but candidate A ("chore(deps): bump
    numpy") has ALREADY been backported (cherry-picked `-x`) onto
    `gitlab/main` by an earlier `--open-mr` run whose MR has since merged —
    simulating the sync boundary on github/main going stale afterwards (see
    `filter_already_applied`'s docstring), so `candidates_after_boundary`
    still (wrongly) returns A alongside the genuinely new B. Returns
    (ci_checkout, gitlab_bare, candidates, boundary_gitlab_sha) with `github`
    and `gitlab` remotes configured and `github/main` already fetched; cwd
    not changed (caller chdir's)."""
    github_repo = tmp_path / "github_repo"
    _init_repo(github_repo)
    _commit(github_repo, "f.txt", "one\n", f"Initial commit\n\nGitLab-Commit: {_FAKE_SHA}")
    candidate_a_sha = _commit(github_repo, "f.txt", "two\n", "chore(deps): bump numpy (dependabot)")
    _commit(github_repo, "f.txt", "three\n", "fix: outside PR merged straight to main")

    gitlab_seed = tmp_path / "gitlab_seed"
    _init_repo(gitlab_seed)
    _commit(gitlab_seed, "f.txt", "one\n", "gitlab base commit")
    boundary_gitlab_sha = _git(gitlab_seed, "rev-parse", "HEAD").stdout.strip()
    # Simulate an earlier --open-mr run's cherry-pick landing (and its MR
    # merging) — candidate A is already on gitlab/main, with its `-x` trailer.
    _git(gitlab_seed, "remote", "add", "github", str(github_repo))
    _git(gitlab_seed, "fetch", "-q", "github", "main")
    _git(gitlab_seed, "cherry-pick", "-x", candidate_a_sha)

    gitlab_bare = tmp_path / "gitlab.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(gitlab_bare))
    _git(gitlab_seed, "remote", "add", "origin", str(gitlab_bare))
    _git(gitlab_seed, "push", "-q", "origin", "main")

    ci_checkout = tmp_path / "ci_checkout"
    _init_repo(ci_checkout)
    _commit(ci_checkout, "h.txt", "ci base\n", "ci checkout base")
    _git(ci_checkout, "remote", "add", "github", str(github_repo))
    _git(ci_checkout, "remote", "add", "gitlab", str(gitlab_bare))
    _git(ci_checkout, "fetch", "github", "main")

    import os

    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        boundary = backport.find_sync_boundary("github/main")
        assert boundary is not None
        candidates = backport.candidates_after_boundary("github/main", boundary)
    finally:
        os.chdir(old_cwd)
    # The stale boundary still lists BOTH — this is the bug's precondition.
    assert [subject for _sha, subject in candidates] == [
        "chore(deps): bump numpy (dependabot)",
        "fix: outside PR merged straight to main",
    ]
    return ci_checkout, gitlab_bare, candidates, boundary_gitlab_sha


def test_filter_already_applied_skips_backported_keeps_new(tmp_path: Path) -> None:
    ci_checkout, _gitlab_bare, candidates, boundary_gitlab_sha = (
        _make_open_mr_fixture_with_prior_backport(
            tmp_path,
        )
    )

    import os

    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        _git(ci_checkout, "fetch", "gitlab", "main")
        filtered = backport.filter_already_applied(candidates, "gitlab/main", boundary_gitlab_sha)
    finally:
        os.chdir(old_cwd)

    assert [subject for _sha, subject in filtered] == ["fix: outside PR merged straight to main"]


def test_run_open_mr_skips_already_applied_candidate_and_backports_new_one(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Recurrence guard for the boundary-freeze bug: a scheduled run whose
    candidate list still (via a stale boundary) contains an already-applied
    commit must drop it — not let the cherry-pick land empty and abort — and
    must still backport whatever genuinely new candidate rides along with
    it."""
    ci_checkout, gitlab_bare, candidates, boundary_gitlab_sha = (
        _make_open_mr_fixture_with_prior_backport(
            tmp_path,
        )
    )
    fake_http = _FakeHttp()
    monkeypatch.setattr(backport, "_http_request", fake_http)
    monkeypatch.setenv("BACKPORT_TOKEN", "test-backport-token")

    import argparse
    import os

    args = argparse.Namespace(
        gitlab_remote_name="gitlab",
        gitlab_remote_url=None,
        target_branch="main",
        mr_host="https://gitlab.example",
        mr_project="anhahn/spectrafit-core",
    )

    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        rc = backport.run_open_mr(args, "github/main", candidates, boundary_gitlab_sha)
    finally:
        os.chdir(old_cwd)

    assert rc == 0
    methods = [call[0] for call in fake_http.calls]
    assert methods == ["GET", "POST", "GET"]  # not skipped outright — the new candidate still goes out

    _post_method, _post_url, post_data = fake_http.calls[1]
    assert post_data is not None
    description = str(post_data["description"])
    assert "chore(deps): bump numpy" not in description  # already-applied candidate dropped
    assert "fix: outside PR" in description  # new candidate still included

    branch_name = str(post_data["source_branch"])
    pushed_subjects = _git(
        gitlab_bare,
        "log",
        branch_name,
        "--pretty=format:%s",
    ).stdout.splitlines()
    assert pushed_subjects[0] == "fix: outside PR merged straight to main"
    # The already-applied commit is still on gitlab/main from the PRIOR
    # backport — it must not have been cherry-picked a second time.
    assert pushed_subjects.count("chore(deps): bump numpy (dependabot)") == 1


def test_run_open_mr_all_candidates_already_applied_is_clean_noop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A candidate list that becomes empty after filtering is a clean no-op —
    no branch, no push, no MR, exit 0 — not the empty-cherry-pick abort this
    filter exists to prevent."""
    ci_checkout, gitlab_bare, candidates, boundary_gitlab_sha = (
        _make_open_mr_fixture_with_prior_backport(
            tmp_path,
        )
    )
    already_applied_only = [c for c in candidates if c[1].startswith("chore(deps)")]
    assert len(already_applied_only) == 1

    fake_http = _FakeHttp()
    monkeypatch.setattr(backport, "_http_request", fake_http)
    monkeypatch.setenv("BACKPORT_TOKEN", "test-backport-token")

    import argparse
    import os

    args = argparse.Namespace(
        gitlab_remote_name="gitlab",
        gitlab_remote_url=None,
        target_branch="main",
        mr_host="https://gitlab.example",
        mr_project="anhahn/spectrafit-core",
    )

    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        rc = backport.run_open_mr(args, "github/main", already_applied_only, boundary_gitlab_sha)
    finally:
        os.chdir(old_cwd)

    assert rc == 0
    assert [call[0] for call in fake_http.calls] == ["GET"]  # no POST — nothing left to backport
    branches = _git(gitlab_bare, "branch", "--list").stdout
    assert "backport/github-" not in branches


def _run_open_mr_in(ci_checkout: Path) -> int:
    import argparse
    import os

    args = argparse.Namespace(
        gitlab_remote_name="gitlab",
        gitlab_remote_url=None,
        target_branch="main",
        mr_host="https://gitlab.example",
        mr_project="anhahn/spectrafit-core",
    )
    old_cwd = Path.cwd()
    os.chdir(ci_checkout)
    try:
        candidates = backport.candidates_after_boundary(
            "github/main",
            backport.find_sync_boundary("github/main") or "",
        )
        return backport.run_open_mr(args, "github/main", candidates)
    finally:
        os.chdir(old_cwd)


def _pipeline_posts(fake_http: _FakeHttp) -> list[str]:
    return [
        url for method, url, _ in fake_http.calls if method == "POST" and url.endswith("/pipelines")
    ]


def test_run_open_mr_reuses_gitlabs_own_mr_pipeline(tmp_path: Path, monkeypatch, capsys) -> None:
    """GitLab attached a merge-request pipeline: no second one is started."""
    ci_checkout, _gitlab_bare, _candidates = _make_open_mr_fixture(tmp_path)
    fake_http = _FakeHttp()
    monkeypatch.setattr(backport, "_http_request", fake_http)
    monkeypatch.setenv("BACKPORT_TOKEN", "test-backport-token")

    assert _run_open_mr_in(ci_checkout) == 0
    assert _pipeline_posts(fake_http) == []
    assert "MR pipeline 77" in capsys.readouterr().out


def test_run_open_mr_starts_exactly_one_pipeline_when_gitlab_made_none(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    ci_checkout, _gitlab_bare, _candidates = _make_open_mr_fixture(tmp_path)
    fake_http = _FakeHttp()
    fake_http.mr_result = {"iid": 1, "head_pipeline": None}
    monkeypatch.setattr(backport, "_http_request", fake_http)
    monkeypatch.setattr(backport, "PIPELINE_WAIT_SECONDS", 0)
    monkeypatch.setattr(backport, "_sleep", lambda _s: None)
    monkeypatch.setenv("BACKPORT_TOKEN", "test-backport-token")

    assert _run_open_mr_in(ci_checkout) == 0
    posts = _pipeline_posts(fake_http)
    assert len(posts) == 1
    assert posts[0].endswith("/merge_requests/1/pipelines")
    out = capsys.readouterr().out
    assert "MR pipeline 88" in out
    assert "https://gitlab.example/p/88" in out


def test_run_open_mr_fails_loudly_when_the_pipeline_cannot_be_started(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    import urllib.error

    ci_checkout, _gitlab_bare, _candidates = _make_open_mr_fixture(tmp_path)
    fake_http = _FakeHttp()
    fake_http.mr_result = {"iid": 1, "head_pipeline": None}

    def failing_http(url: str, token: str, method: str = "GET", data=None) -> object:
        if method == "POST" and url.endswith("/pipelines"):
            raise urllib.error.HTTPError(url, 403, "Forbidden", hdrs=None, fp=None)  # type: ignore[arg-type]
        return fake_http(url, token, method, data)

    monkeypatch.setattr(backport, "_http_request", failing_http)
    monkeypatch.setattr(backport, "PIPELINE_WAIT_SECONDS", 0)
    monkeypatch.setattr(backport, "_sleep", lambda _s: None)
    monkeypatch.setenv("BACKPORT_TOKEN", "test-backport-token")

    assert _run_open_mr_in(ci_checkout) == 1
    assert "FAILED to ensure a pipeline for !1 — 403 Forbidden" in capsys.readouterr().out
