#!/usr/bin/env python3
"""Find commits made directly on the GitHub mirror and land them on GitLab.

Helper for the GitHub-mirror-to-GitLab back-merge recipe (see
docs/contributor-guide/github-mirror-workflow.md).

GitHub `main` is a history-free, periodically force-pushed snapshot of GitLab
`main` (see scripts/publish_snapshot.sh): every snapshot's commit message
carries a trailer, ``GitLab-Commit: <full gitlab sha>`` (shared contract —
``SYNC_TRAILER`` / ``parse_sync_trailer`` — defined in scripts/publish_sync.py
and imported from there, never redefined here). Because GitLab and GitHub
histories are otherwise UNRELATED after that rewrite, "commits reachable from
github/main but not from local main" is meaningless: it lists every commit
GitHub has ever had, snapshot included. The only trustworthy boundary is the
newest first-parent commit on github/main that itself carries the trailer —
everything after it, in first-parent order, is either a Dependabot merge or
an outside PR merged straight into the mirror ("GitHub-native work"), which is
exactly what this script hunts for.

Two supported modes:
  1. Default (--github-branch main): boundary-based. Refuses, rather than
     listing everything, when github/main carries no sync trailer yet (mirror
     not yet on trailer-based sync).
  2. Named branch (--github-branch <branch>): a branch that exists on the
     mirror itself — GitHub-native work such as a Dependabot update (direct
     pushes to the mirror are refused, see scripts/guard_public_push.py). Its
     base is the merge-base with github/main, not local main — the branch was
     forked from the mirror's own (unrelated) history, so diffing against
     local main is the same bug.

This direction carries HISTORY, the opposite of the anonymous squash sync in
scripts/publish_sync.py: every GitHub commit lands on GitLab as its own
commit, with its original author name, email, date and message, plus the
``(cherry picked from commit <sha>)`` line ``cherry-pick -x`` appends. A
first-parent merge commit (a PR merged with GitHub's "Create a merge commit"
button) is therefore expanded into the PR's own commits
(``<merge>^1..<merge>^2``) rather than replayed as one ``-m 1`` diff, which
would collapse the PR into a single commit attributed to whoever merged it.
The merge request is opened with ``squash: false`` so GitLab does not undo
that on merge either.

--open-mr additionally cherry-picks the candidates onto a fresh
``backport/github-<YYYYMMDD>`` branch created from ``gitlab/main``, pushes it,
and opens a GitLab merge request via the REST API. Without --open-mr the
script only lists commits and prints the cherry-pick/squash recipe for a
human to run; --open-mr is the scheduled-automation exception to it (see .gitlab/75-backport.yml).

The ``github`` remote is fetched over HTTPS; against a private mirror that
fetch needs ``GITHUB_TOKEN``, which the CI job injects as an
``http.https://github.com/.extraheader`` via ``GIT_CONFIG_*`` environment
variables (never the remote URL or ``.git/config``) — see
.gitlab/75-backport.yml.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish_sync import SYNC_TRAILER, parse_sync_trailer

DEFAULT_GITHUB_REMOTE_URL = "https://github.com/Anselmoo/SpectraFit-Core.git"
DEFAULT_GITLAB_HOST = "https://gitlab.mpcdf.mpg.de"
DEFAULT_GITLAB_PROJECT = "anhahn/spectrafit-core"
BACKPORT_BRANCH_PREFIX = "backport/github-"


def _run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout


def _run_ok(*args: str) -> subprocess.CompletedProcess[str]:
    """Like `_run` but never raises — caller inspects `.returncode`."""
    return subprocess.run(args, capture_output=True, text=True, check=False)


def ensure_remote(remote_name: str, remote_url: str | None) -> None:
    """Ensure `remote_name` exists locally (idempotent).

    No-op if `remote_url` is None — the caller expects the remote (e.g.
    `gitlab`) to already be configured, as it is in a normal GitLab CI
    checkout.
    """
    if remote_url is None:
        return
    existing = subprocess.run(
        ["git", "remote"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if remote_name not in existing:
        subprocess.run(["git", "remote", "add", remote_name, remote_url], check=True)


def fetch_branch(remote_name: str, remote_url: str | None, branch: str) -> None:
    """Ensure `remote_name` exists and fetch `branch` from it."""
    ensure_remote(remote_name, remote_url)
    subprocess.run(["git", "fetch", remote_name, branch], check=True)


def commit_message(sha: str) -> str:
    """Full commit message (subject + body) for `sha`."""
    return _run("git", "log", "-1", "--format=%B", sha)


def commit_subject(message: str) -> str:
    """First line of a full commit message."""
    lines = message.splitlines()
    return lines[0] if lines else ""


def find_sync_boundary(remote_ref: str) -> str | None:
    """Return the newest first-parent commit on `remote_ref` carrying SYNC_TRAILER.

    None if none of them do (mirror not yet on trailer-based sync — see
    module docstring).
    """
    raw_shas = _run("git", "rev-list", "--first-parent", remote_ref).splitlines()
    for raw_sha in raw_shas:
        sha = raw_sha.strip()
        if not sha:
            continue
        if parse_sync_trailer(commit_message(sha)) is not None:
            return sha
    return None


def expand_merge(sha: str) -> list[str]:
    """The commits `sha` stands for on the backport, oldest first.

    A non-merge commit stands for itself. A merge commit (a GitHub PR merged
    with "Create a merge commit") stands for the PR's own commits — those
    reachable from its second parent but not its first,
    ``<sha>^1..<sha>^2`` — so each lands on GitLab individually with its
    original author and message instead of as one ``-m 1`` diff attributed
    to whoever pressed the merge button (see module docstring).

    Merges nested inside the PR branch (e.g. "Update branch" merges of main
    into it) are left out with ``--no-merges``: their content is either
    already on the first-parent side or carried by the PR commits around
    them. If a PR somehow contributes no non-merge commit at all, the merge
    itself is returned so `cherry_pick_onto_branch`'s ``-m 1`` fallback still
    carries its diff rather than silently dropping it.
    """
    parents = _commit_parents(sha)
    if len(parents) < 2:
        return [sha]
    pr_commits = [
        line.strip()
        for line in _run(
            "git",
            "rev-list",
            "--reverse",
            "--no-merges",
            f"{parents[0]}..{parents[1]}",
        ).splitlines()
        if line.strip()
    ]
    return pr_commits or [sha]


def candidates_after_boundary(remote_ref: str, boundary_sha: str) -> list[tuple[str, str]]:
    """(sha, subject) for commits after `boundary_sha`, oldest first.

    GitHub-native work pending backport, up to `remote_ref`: the first-parent
    commits strictly after the boundary, with every merge among them expanded
    into its PR's individual commits (see `expand_merge`). Defensively skips
    any commit that itself carries SYNC_TRAILER (a second snapshot republish
    should never be treated as something to cherry-pick).
    """
    raw_shas = _run(
        "git",
        "rev-list",
        "--first-parent",
        "--reverse",
        f"{boundary_sha}..{remote_ref}",
    ).splitlines()
    candidates: list[tuple[str, str]] = []
    for raw_sha in raw_shas:
        first_parent_sha = raw_sha.strip()
        if not first_parent_sha:
            continue
        for sha in expand_merge(first_parent_sha):
            message = commit_message(sha)
            if parse_sync_trailer(message) is not None:
                continue
            candidates.append((sha, commit_subject(message)))
    return candidates


def candidates_on_feature_branch(remote_ref: str, github_main_ref: str) -> list[tuple[str, str]]:
    """(sha, subject) for commits on `remote_ref` since its merge-base with `github_main_ref`.

    Oldest first. The base is the mirror's own main, not local main — see
    module docstring.
    """
    merge_base = _run("git", "merge-base", github_main_ref, remote_ref).strip()
    raw_shas = _run(
        "git",
        "rev-list",
        "--reverse",
        f"{merge_base}..{remote_ref}",
    ).splitlines()
    candidates: list[tuple[str, str]] = []
    for raw_sha in raw_shas:
        sha = raw_sha.strip()
        if not sha:
            continue
        message = commit_message(sha)
        if parse_sync_trailer(message) is not None:
            continue
        candidates.append((sha, commit_subject(message)))
    return candidates


_CHERRY_PICK_X_RE = re.compile(r"\(cherry picked from commit ([0-9a-fA-F]{40})\)")


def already_applied_shas(gitlab_ref: str) -> set[str]:
    """Full GitHub SHAs already cherry-picked (via `-x`) onto `gitlab_ref`.

    Scans every commit message reachable from `gitlab_ref` for the "(cherry
    picked from commit <sha>)" trailer `git cherry-pick -x` writes (see
    `cherry_pick_onto_branch`) — the cheap, primary signal that a candidate
    has already been backported by an earlier `--open-mr` run.
    """
    log = _run("git", "log", gitlab_ref, "--format=%B")
    return {match.group(1) for match in _CHERRY_PICK_X_RE.finditer(log)}


def _commit_parents(sha: str) -> list[str]:
    """Full parent SHAs of `sha`, in parent order (empty for a root commit)."""
    parts = _run("git", "rev-list", "--parents", "-n", "1", sha).split()
    return parts[1:]


def _patch_id(diff_text: str) -> str | None:
    """`git patch-id --stable`'s id for a unified `diff_text`, or None if empty."""
    if not diff_text.strip():
        return None
    result = subprocess.run(
        ["git", "patch-id", "--stable"],
        input=diff_text,
        capture_output=True,
        text=True,
        check=True,
    )
    line = result.stdout.strip()
    return line.split()[0] if line else None


def _commit_patch_id(sha: str) -> str | None:
    """`sha`'s patch-id against its first parent (its full diff for a root commit).

    A merge commit (see `_commit_parents`) is diffed against its FIRST parent
    only — the same first-parent view `candidates_after_boundary` selects
    candidates by, and the same parent `-m 1` replays against in
    `cherry_pick_onto_branch`.
    """
    parents = _commit_parents(sha)
    diff_text = (
        _run("git", "diff", parents[0], sha)
        if parents
        else _run("git", "show", "--format=", "-p", sha)
    )
    return _patch_id(diff_text)


def _patch_ids_in_range(rev_range: str) -> set[str]:
    """Patch-ids of every first-parent commit in `rev_range` (e.g. `"a..b"`).

    An empty `rev_range` (no lower bound available) yields an empty set
    rather than scanning unbounded history — callers without a boundary sha
    fall back to the `-x`-trailer check alone (see `filter_already_applied`).
    """
    if not rev_range:
        return set()
    log_output = _run("git", "log", "--first-parent", "-p", rev_range)
    if not log_output.strip():
        return set()
    result = subprocess.run(
        ["git", "patch-id", "--stable"],
        input=log_output,
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.split()[0] for line in result.stdout.splitlines() if line.strip()}


def filter_already_applied(
    candidates: list[tuple[str, str]],
    gitlab_ref: str,
    boundary_gitlab_sha: str | None,
) -> list[tuple[str, str]]:
    """Drop candidates already present on `gitlab_ref`.

    The backport boundary on `github/main` (see `find_sync_boundary`) only
    advances on a GitLab -> GitHub sync whose CONTENT differs — a
    backport-only round does not by itself produce that, since it makes
    GitLab's tree converge on GitHub's, not diverge (see
    `scripts/publish_sync.py`'s `sync_needed`). Left unfiltered, a scheduled
    `--open-mr` run after a backport MR lands would re-select the exact same
    already-applied candidates, the cherry-pick onto them would land empty,
    and the run would abort instead of finding whatever genuinely new work
    sits behind them.

    Primary signal: the candidate's full SHA appears in a `(cherry picked
    from commit ...)` trailer somewhere in `gitlab_ref`'s history (written by
    an earlier `-x` cherry-pick). Secondary signal: the candidate's patch-id
    matches a first-parent commit in `boundary_gitlab_sha..gitlab_ref` (a
    backport that landed without a `-x` trailer, e.g. hand-resolved). Without
    a `boundary_gitlab_sha` (feature-branch mode has none), only the primary
    signal applies.
    """
    applied_x_shas = already_applied_shas(gitlab_ref)
    rev_range = f"{boundary_gitlab_sha}..{gitlab_ref}" if boundary_gitlab_sha else ""
    applied_patch_ids = _patch_ids_in_range(rev_range)
    remaining: list[tuple[str, str]] = []
    for sha, subject in candidates:
        if sha in applied_x_shas:
            continue
        patch_id = _commit_patch_id(sha)
        if patch_id is not None and patch_id in applied_patch_ids:
            continue
        remaining.append((sha, subject))
    return remaining


def _print_recipe(
    remote_ref: str,
    local_ref: str,
    candidates: list[tuple[str, str]],
    squash: bool,
) -> None:
    print(
        f"backport_from_github: {len(candidates)} commit(s) on {remote_ref} pending review:",
    )
    for sha, subject in candidates:
        print(f"  {sha[:10]}  {subject}")
    print()
    if squash:
        print("Review the commits above, then squash-merge onto a feature branch:")
        print(f"  git checkout -b backport/<description> {local_ref}")
        print(f"  git merge --squash {remote_ref}")
        print("  git commit")
    else:
        print("Review each, then cherry-pick the ones you want onto a feature branch:")
        print(f"  git checkout -b backport/<description> {local_ref}")
        print(f"  git cherry-pick {' '.join(sha[:10] for sha, _ in candidates)}")


# ---------------------------------------------------------------------------
# --open-mr: cherry-pick onto a fresh branch and open a GitLab MR via the REST
# API. Everything below this point is only reached with --open-mr.
# ---------------------------------------------------------------------------


def _http_request(
    url: str,
    token: str,
    method: str = "GET",
    data: dict[str, object] | None = None,
) -> object:
    """Single low-level GitLab REST API call — the one seam tests mock."""
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("PRIVATE-TOKEN", token)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _api_base(host: str, project: str) -> str:
    encoded_project = urllib.parse.quote(str(project), safe="")
    return f"{host.rstrip('/')}/api/v4/projects/{encoded_project}"


def open_backport_mr_exists(host: str, project: str, token: str) -> bool:
    """True if an open MR whose source branch starts with BACKPORT_BRANCH_PREFIX exists.

    This is the idempotent-schedule guard.
    """
    url = f"{_api_base(host, project)}/merge_requests?state=opened&per_page=100"
    results = _http_request(url, token, method="GET")
    if not isinstance(results, list):
        return False
    return any(
        isinstance(mr, dict) and str(mr.get("source_branch", "")).startswith(BACKPORT_BRANCH_PREFIX)
        for mr in results
    )


def next_backport_branch_name(gitlab_remote_name: str, today: datetime.date | None = None) -> str:
    """Return `backport/github-<YYYYMMDD>`, or that name suffixed -2, -3, ....

    The suffix is added if that name (or an earlier suffix of it) already
    exists as a branch on `gitlab_remote_name`.
    """
    stamp = (today or datetime.datetime.now(tz=datetime.UTC).date()).strftime("%Y%m%d")
    base = f"{BACKPORT_BRANCH_PREFIX}{stamp}"
    existing_output = _run("git", "ls-remote", "--heads", gitlab_remote_name)
    existing_refs = {
        line.partition("\t")[2].removeprefix("refs/heads/")
        for line in existing_output.splitlines()
        if line.strip()
    }
    if base not in existing_refs:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing_refs:
        suffix += 1
    return f"{base}-{suffix}"


def _cherry_pick_supports_empty_drop() -> bool:
    """True if the installed git's `cherry-pick` accepts `--empty=drop` (git>=2.45)."""
    result = _run_ok("git", "cherry-pick", "-h")
    help_text = (result.stdout or "") + (result.stderr or "")
    return "--empty" in help_text


def _cherry_pick_became_empty(result: subprocess.CompletedProcess[str]) -> bool:
    """True if a failed `cherry-pick` failed because it produced an empty commit.

    This is the stop git makes (without `--empty=drop`) when a candidate's
    diff is already present in the tree — not a real conflict.
    """
    combined = (result.stdout or "") + (result.stderr or "")
    return "cherry-pick is now empty" in combined or "nothing to commit" in combined


def cherry_pick_onto_branch(
    branch_name: str,
    base_ref: str,
    candidates: list[tuple[str, str]],
) -> str | None:
    """Create `branch_name` from `base_ref` and cherry-pick each candidate (`-x`, oldest first).

    Each candidate keeps its original author name, email and date — plain
    `git cherry-pick` never rewrites the author, only the committer — and
    `-x` appends the ``(cherry picked from commit <sha>)`` line that
    `already_applied_shas` later keys on. Candidates are never squashed.

    Merge candidates normally never reach this point: `candidates_after_boundary`
    expands them into their PR commits (see `expand_merge`). As a defensive
    fallback — a feature-branch-mode merge, or a PR with no non-merge commit —
    a candidate with more than one parent is replayed with `-m 1` against its
    first parent, since plain `cherry-pick` refuses a merge commit outright.

    A candidate that turns out to already be applied — its diff is empty
    against the branch's current tip — is skipped rather than treated as a
    conflict: `--empty=drop` does this natively when the installed git
    supports it (>=2.45); on an older git the "cherry-pick is now empty" stop
    is detected and resolved with `git cherry-pick --skip`.
    `filter_already_applied` is expected to have already removed most of
    these before this function ever runs; this is the defense-in-depth layer
    for what it can't catch (e.g. a hand-resolved backport with no `-x`
    trailer and a patch-id outside `filter_already_applied`'s scanned range).

    Returns None on success, or the failing sha on the first REAL conflict —
    the caller aborts the pick and reports non-zero; no auto-resolve, ever.
    """
    subprocess.run(["git", "checkout", "-b", branch_name, base_ref], check=True)
    empty_drop_supported = _cherry_pick_supports_empty_drop()
    for sha, _subject in candidates:
        command = ["git", "cherry-pick", "-x"]
        if len(_commit_parents(sha)) > 1:
            command += ["-m", "1"]
        if empty_drop_supported:
            command += ["--empty=drop"]
        command.append(sha)
        result = _run_ok(*command)
        if result.returncode != 0:
            if not empty_drop_supported and _cherry_pick_became_empty(result):
                skip_result = _run_ok("git", "cherry-pick", "--skip")
                if skip_result.returncode == 0:
                    continue
            subprocess.run(["git", "cherry-pick", "--abort"], check=False)
            return sha
    return None


def push_backport_branch(gitlab_remote_name: str, branch_name: str) -> None:
    """Push the freshly cherry-picked local branch to `gitlab_remote_name`."""
    subprocess.run(
        ["git", "push", gitlab_remote_name, f"{branch_name}:{branch_name}"],
        check=True,
    )


def open_merge_request(
    host: str,
    project: str,
    token: str,
    source_branch: str,
    target_branch: str,
    candidates: list[tuple[str, str]],
) -> str:
    """POST the merge request; returns its web_url."""
    body_lines = [
        (
            "Automated backport of GitHub-native work onto GitLab, cherry-picked "
            "with `-x` by `scripts/backport_from_github.py --open-mr`."
        ),
        "",
        "Commits:",
    ]
    body_lines.extend(f"- {sha[:10]} {subject}" for sha, subject in candidates)
    payload: dict[str, object] = {
        "source_branch": source_branch,
        "target_branch": target_branch,
        "title": f"Backport GitHub main @ {source_branch.removeprefix(BACKPORT_BRANCH_PREFIX)}",
        "description": "\n".join(body_lines),
        "remove_source_branch": True,
        # History-preserving direction: each GitHub commit must land on
        # GitLab individually. Set explicitly rather than inheriting the
        # project's squash_option default ("Require" would still override
        # it — keep the project on "Allow"/"Do not allow").
        "squash": False,
    }
    url = f"{_api_base(host, project)}/merge_requests"
    result = _http_request(url, token, method="POST", data=payload)
    return str(result.get("web_url", "")) if isinstance(result, dict) else ""


def run_open_mr(
    args: argparse.Namespace,
    remote_main_ref: str,
    candidates: list[tuple[str, str]],
    boundary_gitlab_sha: str | None = None,
) -> int:
    """Cherry-pick `candidates` onto a fresh backport branch off gitlab/main, then push and open the MR.

    `remote_main_ref` (e.g. "github/main") is only used in log/print output,
    not for git plumbing — the caller already resolved `candidates` from it.

    `boundary_gitlab_sha` (the GitLab SHA embedded in the boundary commit's
    `GitLab-Commit` trailer, main/boundary mode only — `main()` passes None
    for feature-branch mode) bounds `filter_already_applied`'s secondary
    patch-id scan; see that function's docstring for why the filter runs at
    all.
    """
    host = args.mr_host or os.environ.get("CI_SERVER_URL") or DEFAULT_GITLAB_HOST
    project = args.mr_project or os.environ.get("CI_PROJECT_ID") or DEFAULT_GITLAB_PROJECT
    token = os.environ.get("BACKPORT_TOKEN")
    if not token:
        print(
            "backport_from_github: --open-mr requires BACKPORT_TOKEN in the "
            "environment (a project access token with api + write_repository "
            "— CI_JOB_TOKEN cannot push).",
        )
        return 1

    try:
        if open_backport_mr_exists(host, project, token):
            print(
                f"backport_from_github: an open MR from a {BACKPORT_BRANCH_PREFIX}* "
                "branch already exists — skipping (idempotent schedule).",
            )
            return 0
    except urllib.error.HTTPError as exc:
        print(f"backport_from_github: FAILED to list merge requests — {exc.code} {exc.reason}")
        return 1

    try:
        fetch_branch(args.gitlab_remote_name, args.gitlab_remote_url, args.target_branch)
    except subprocess.CalledProcessError as exc:
        print(
            f"backport_from_github: FAILED to fetch gitlab {args.target_branch} — {exc.stderr or exc}",
        )
        return 1

    gitlab_base_ref = f"{args.gitlab_remote_name}/{args.target_branch}"

    candidates = filter_already_applied(candidates, gitlab_base_ref, boundary_gitlab_sha)
    if not candidates:
        print(
            f"backport_from_github: every candidate is already present on "
            f"{gitlab_base_ref} (backported by an earlier run) — nothing to "
            "backport. Clean no-op.",
        )
        return 0

    branch_name = next_backport_branch_name(args.gitlab_remote_name)
    print(f"backport_from_github: cherry-picking onto {branch_name} (from {gitlab_base_ref})")

    failing_sha = cherry_pick_onto_branch(branch_name, gitlab_base_ref, candidates)
    if failing_sha is not None:
        print(
            f"backport_from_github: cherry-pick of {failing_sha[:10]} conflicted — "
            "aborted. No auto-resolve; resolve it by hand and open the MR "
            "manually.",
        )
        return 1

    try:
        push_backport_branch(args.gitlab_remote_name, branch_name)
    except subprocess.CalledProcessError as exc:
        print(f"backport_from_github: FAILED to push {branch_name} — {exc.stderr or exc}")
        return 1

    try:
        web_url = open_merge_request(
            host,
            project,
            token,
            source_branch=branch_name,
            target_branch=args.target_branch,
            candidates=candidates,
        )
    except urllib.error.HTTPError as exc:
        print(f"backport_from_github: FAILED to open the merge request — {exc.code} {exc.reason}")
        return 1

    print(f"backport_from_github: opened merge request {web_url or '(no web_url in response)'}")
    return 0


def main() -> int:
    """Parse CLI args and either print the pending-backport recipe or act on it.

    With --open-mr, cherry-pick the candidates and open the GitLab merge
    request instead of just printing the recipe.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Find commits made directly on the GitHub mirror and land them on "
            "GitLab, either as a printed cherry-pick/squash recipe or (--open-mr) "
            "as an actual cherry-picked branch + merge request."
        ),
    )
    parser.add_argument("--remote-name", default="github")
    parser.add_argument("--remote-url", default=DEFAULT_GITHUB_REMOTE_URL)
    parser.add_argument(
        "--github-branch",
        default="main",
        help=(
            "GitHub branch to check. Default 'main' is boundary-based (see "
            "module docstring); pass a feature-branch name for the "
            "GitHub-first iteration lane."
        ),
    )
    parser.add_argument(
        "--local-ref",
        default="main",
        help="local branch named in the printed recipe's `git checkout -b` line",
    )
    parser.add_argument(
        "--squash",
        action="store_true",
        help=(
            "Suggest a single squash-merge commit instead of a per-SHA cherry-pick "
            "list — use for a WIP-heavy feature branch. Ignored with --open-mr, "
            "which always cherry-picks individually."
        ),
    )
    parser.add_argument(
        "--open-mr",
        action="store_true",
        help=(
            "Cherry-pick the candidates onto a fresh backport/github-<date> "
            "branch off gitlab/main, push it, and open a GitLab merge request. "
            "Requires BACKPORT_TOKEN. See .gitlab/75-backport.yml."
        ),
    )
    parser.add_argument("--gitlab-remote-name", default="gitlab")
    parser.add_argument(
        "--gitlab-remote-url",
        default=os.environ.get("CI_REPOSITORY_URL"),
        help="only needed if the 'gitlab' remote isn't already configured",
    )
    parser.add_argument("--target-branch", default="main", help="GitLab branch to base/target")
    parser.add_argument(
        "--mr-host",
        default=None,
        help=f"GitLab host (default: $CI_SERVER_URL or {DEFAULT_GITLAB_HOST})",
    )
    parser.add_argument(
        "--mr-project",
        default=None,
        help=f"GitLab project (default: $CI_PROJECT_ID or {DEFAULT_GITLAB_PROJECT})",
    )
    args = parser.parse_args()

    if args.squash and args.open_mr:
        parser.error("--squash and --open-mr are mutually exclusive")

    try:
        fetch_branch(args.remote_name, args.remote_url, args.github_branch)
    except subprocess.CalledProcessError as exc:
        print(f"backport_from_github: FAILED to fetch — {exc.stderr or exc}")
        return 1

    remote_ref = f"{args.remote_name}/{args.github_branch}"
    boundary_gitlab_sha: str | None = None

    if args.github_branch == "main":
        boundary_sha = find_sync_boundary(remote_ref)
        if boundary_sha is None:
            print(
                f"backport_from_github: refusing — no commit on {remote_ref} carries "
                f"a '{SYNC_TRAILER}:' trailer yet (mirror not yet on trailer-based "
                "sync). Listing 'everything' would be meaningless: GitLab and "
                "GitHub histories are unrelated after the orphan-snapshot rewrite.",
            )
            return 1
        candidates = candidates_after_boundary(remote_ref, boundary_sha)
        # The GitLab sha the boundary commit's sync trailer names — the range
        # start `filter_already_applied` scans from when --open-mr runs (see
        # its docstring for why the boundary can go stale after a backport).
        boundary_gitlab_sha = parse_sync_trailer(commit_message(boundary_sha))
    else:
        try:
            fetch_branch(args.remote_name, args.remote_url, "main")
        except subprocess.CalledProcessError as exc:
            print(
                f"backport_from_github: FAILED to fetch {args.remote_name}/main — {exc.stderr or exc}",
            )
            return 1
        github_main_ref = f"{args.remote_name}/main"
        candidates = candidates_on_feature_branch(remote_ref, github_main_ref)

    if not candidates:
        print(
            f"backport_from_github: no commits on {remote_ref} pending backport.",
        )
        return 0

    if args.open_mr:
        return run_open_mr(args, remote_ref, candidates, boundary_gitlab_sha)

    _print_recipe(remote_ref, args.local_ref, candidates, args.squash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
