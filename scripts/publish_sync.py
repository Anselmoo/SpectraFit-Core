#!/usr/bin/env python3
"""GitLab -> GitHub sync: one anonymous bot commit per sync, append-only.

Replaces the history-discarding orphan snapshot (``scripts/publish_snapshot.sh``,
kept only as the manual ``publish:github:reset`` emergency re-baseline job) with
a normal, reviewable PR: build ONE commit whose TREE is the current GitLab
``HEAD`` tree reduced to the public publish scope
(``scripts/publish_exclusions.py``), whose single PARENT is the
already-published GitHub ``main``, push it to a dedicated sync branch, and open
(or update) a PR for it. Because the commit's parent is the previous GitHub
``main`` — not an orphan root — GitHub's own history for the mirror grows
append-only, one sync commit per GitLab sync, instead of being discarded on
every publish.

This direction is ANONYMOUS by contract: the sync commit's author AND
committer are the bot identity (``_BOT_NAME`` / ``_BOT_EMAIL``), its message is
a fixed subject plus generic text, and the only GitLab-derived content in it
is the ``GitLab-Commit: <full sha>`` trailer (``SYNC_TRAILER`` /
``build_sync_message`` below) marking the sync boundary. No GitLab commit
message, author, or history crosses over. (The history-preserving direction is
``scripts/backport_from_github.py``.)

Landing is a FAST-FORWARD push of that exact commit, never a GitHub merge
button: a squash merge on GitHub — including GraphQL auto-merge — re-authors
the commit to the PR author (the token's owner) and sets the committer to
``GitHub <noreply@github.com>``, which would break the anonymity contract. So
after pushing the sync branch and opening the PR (which runs the mirror's CI),
this script reads the base branch's required status checks from the
repository's rulesets, waits until every one of them has passed on the sync
commit, and only then pushes the same SHA to ``main`` without ``--force``
(``land_fast_forward``). GitHub marks the PR merged by itself once its head
commit is on the base branch. Every git WRITE — the sync-branch push and the
landing push — goes through one remote (``--push-remote``, an SSH remote
authenticated by a deploy key that is the ONLY bypass actor on the mirror's
rulesets), so no personal account ever needs push rights on the mirror;
``GITHUB_TOKEN`` is only used to fetch and for the REST API. A rejected non-fast-forward
(``main`` moved since the commit was built) aborts loudly instead of being
forced. No required check configured means no landing: this script never
lands unguarded.

The commit's author and committer dates are pinned to the GitLab ``HEAD``
commit date, so rebuilding the same sync (same tree, same parent, same
GitLab SHA) yields the SAME commit SHA. A run that times out waiting for
checks therefore resumes on the next run instead of restarting CI.

Tree-building never touches the real working tree or the real index: it reads
the GitLab ``HEAD`` tree into a throwaway index file (``GIT_INDEX_FILE``
pointed at a path under a ``tempfile.TemporaryDirectory()``, well outside
``.git/``), removes every non-published path from *that* index with
``git update-index --force-remove`` (unlike ``git rm``, this does not compare
against the working tree or HEAD, so it works even though the throwaway index
was never checked out anywhere — see ``scripts/publish_remove_excluded.py``'s
docstring for the sibling gotcha on the orphan-branch path this script
replaces), and writes the result with ``git write-tree``. The real ``git
status`` of the caller's checkout is unaffected.

CWE-522 hardening: ``GITHUB_TOKEN`` is never embedded in a remote URL or
written to ``.git/config`` — git fetch auth over HTTPS uses the same
``GIT_CONFIG_COUNT``/``GIT_CONFIG_KEY_0``/``GIT_CONFIG_VALUE_0``
``http.extraheader`` mechanism as ``scripts/publish_snapshot.sh``, scoped to
``https://github.com/`` and passed only via the child process's environment.
The fetch is authenticated because the mirror may be private. The GitHub
REST calls reuse the plain ``urllib``-based request helper pattern from
``scripts/purge_github_actions_runs.py`` (no extra dependency).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish_exclusions import is_excluded

# Shared with scripts/backport_from_github.py (the GitHub -> GitLab direction)
# so the trailer name cannot drift between the two sync scripts.
SYNC_TRAILER = "GitLab-Commit"

_API_ROOT = "https://api.github.com"

# Same bot identity scripts/publish_snapshot.sh sets via `git config` before
# calling `rrt git publish-snapshot` (which itself runs `git commit -m ...`
# internally) — kept identical so both sync directions attribute to the same
# recognizable, non-personal identity. It is the bot account of the
# `spectrafit-core-sync` GitHub App (app id 5097744, bot user id 334580965):
# GitHub attributes commits carrying this noreply address to that bot, never to
# a person, and the App needs no permissions or installation for that.
_BOT_NAME = "spectrafit-core-sync[bot]"
_BOT_EMAIL = "334580965+spectrafit-core-sync[bot]@users.noreply.github.com"

_SYNC_SUBJECT = "sync: gitlab main"
_SYNC_TEXT = (
    "Automated sync of GitLab `main` into the GitHub mirror. This branch is "
    "force-pushed on every sync — do not build on it by hand."
)

# Check-run conclusions GitHub itself accepts for a required check; every
# other conclusion of a COMPLETED run counts as a failure.
_PASSING_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})

CheckOutcome = Literal["success", "failure", "timeout"]


class SyncError(Exception):
    """Raised for an unrecoverable publish_sync failure (git or GitHub API)."""


# --------------------------------------------------------------------------
# Pure logic — no subprocess/network calls. Unit-tested directly.
# --------------------------------------------------------------------------


def excluded_tracked_paths(tracked: list[str]) -> list[str]:
    """Return the subset of `tracked` paths outside the public publish scope."""
    return [path for path in tracked if is_excluded(path)]


def parse_sync_trailer(message: str) -> str | None:
    """Return the `SYNC_TRAILER` value from a commit message, or None.

    Matches a line of the exact form ``"<SYNC_TRAILER>: <value>"`` (surrounding
    whitespace on the line is ignored), the same shape
    ``scripts/publish_snapshot.sh`` writes for the orphan-snapshot commits this
    script's sync commits also carry.
    """
    prefix = f"{SYNC_TRAILER}: "
    for line in message.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            value = stripped[len(prefix) :].strip()
            return value or None
    return None


def build_sync_message(sha: str) -> tuple[str, str]:
    """Return (subject, body) for the sync commit built from GitLab HEAD `sha`.

    Both parts are fixed text except the `SYNC_TRAILER` line at the end of
    `body`, which names the full GitLab SHA — the one piece of GitLab state the
    anonymity contract lets through (see module docstring).
    """
    return _SYNC_SUBJECT, f"{_SYNC_TEXT}\n\n{SYNC_TRAILER}: {sha}"


def sync_needed(filtered_tree: str, remote_tree: str) -> bool:
    """Return True when the filtered GitLab tree differs from the published one."""
    return filtered_tree != remote_tree


def required_check_contexts(rules: list[dict[str, Any]]) -> list[str]:
    """Required status-check contexts from a ``rules/branches/<branch>`` response."""
    contexts: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("type") != "required_status_checks":
            continue
        parameters = rule.get("parameters") or {}
        for check in parameters.get("required_status_checks") or []:
            context = check.get("context") if isinstance(check, dict) else None
            if context and context not in contexts:
                contexts.append(str(context))
    return contexts


def evaluate_checks(
    contexts: list[str],
    check_runs: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
) -> CheckOutcome | None:
    """Decide the required checks' state for one commit.

    Returns "success" once every context has passed, "failure" as soon as any
    has failed, and None while at least one is still pending or has not been
    reported at all. A context may be satisfied by a check run (matched on
    ``name``) or a commit status (matched on ``context``), the two ways GitHub
    reports a required check.
    """
    pending = False
    for context in contexts:
        runs = [run for run in check_runs if run.get("name") == context]
        states = [status for status in statuses if status.get("context") == context]
        if any(
            run.get("status") == "completed" and run.get("conclusion") not in _PASSING_CONCLUSIONS
            for run in runs
        ) or any(status.get("state") in {"failure", "error"} for status in states):
            return "failure"
        passed = any(
            run.get("status") == "completed" and run.get("conclusion") in _PASSING_CONCLUSIONS
            for run in runs
        ) or any(status.get("state") == "success" for status in states)
        if not passed:
            pending = True
    return None if pending else "success"


# --------------------------------------------------------------------------
# Git plumbing — real subprocess calls, but all pure-git (no network).
# --------------------------------------------------------------------------


def _git(
    repo_root: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def fetch_remote(repo_root: Path, remote: str, branch: str, token: str | None = None) -> None:
    """Fetch `branch` from `remote` (read-only).

    With `token`, the fetch carries the same ``https://github.com/``-scoped
    auth header as the push (`_github_auth_env`) — a private mirror refuses
    anonymous fetches.
    """
    env = {**os.environ, **_github_auth_env(token)} if token else None
    _git(repo_root, "fetch", remote, branch, env=env)


def rev_parse(repo_root: Path, ref: str) -> str:
    """Resolve `ref` (a commit, branch, or `<ref>^{tree}`) to its full SHA."""
    return _git(repo_root, "rev-parse", ref).stdout.strip()


def commit_date(repo_root: Path, ref: str) -> str:
    """`ref`'s committer date, strict ISO 8601."""
    return _git(repo_root, "log", "-1", "--format=%cI", ref).stdout.strip()


def tracked_paths(repo_root: Path, ref: str) -> list[str]:
    """Return every path git tracks in `ref`'s tree, repo-root-relative."""
    return _git(repo_root, "ls-tree", "-r", "--name-only", ref).stdout.splitlines()


def build_filtered_tree(repo_root: Path, ref: str = "HEAD") -> str:
    """Build (and return the SHA of) `ref`'s tree with excluded paths removed.

    Uses a throwaway `GIT_INDEX_FILE` outside `.git/` — never touches the
    caller's real working tree or the real index. `git update-index
    --force-remove` (not `git rm`) is used deliberately: it removes an entry
    from the given index unconditionally, with no "does this match the
    working tree / HEAD" safety check to sidestep (the same class of check
    that forces `scripts/publish_remove_excluded.py` to pass `-f` to `git rm`
    on rrt's orphan branch — see that module's docstring).
    """
    to_remove = excluded_tracked_paths(tracked_paths(repo_root, ref))
    with tempfile.TemporaryDirectory() as tmp_dir:
        index_path = Path(tmp_dir) / "sync-index"
        env = {**os.environ, "GIT_INDEX_FILE": str(index_path)}
        _git(repo_root, "read-tree", ref, env=env)
        if to_remove:
            _git(repo_root, "update-index", "--force-remove", "--", *to_remove, env=env)
        return _git(repo_root, "write-tree", env=env).stdout.strip()


def commit_sync_tree(
    repo_root: Path,
    tree_sha: str,
    parent_sha: str,
    subject: str,
    body: str,
    date: str,
) -> str:
    """Create (but do not push) the sync commit; return its SHA.

    Author and committer — name, email AND date — are all set explicitly, so
    nothing from the caller's environment or git config (a developer running
    this locally, a CI runner's identity) can reach the commit. `date` is the
    GitLab HEAD commit date (see module docstring: it makes the SHA
    reproducible).
    """
    message = f"{subject}\n\n{body}"
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": _BOT_NAME,
        "GIT_AUTHOR_EMAIL": _BOT_EMAIL,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_NAME": _BOT_NAME,
        "GIT_COMMITTER_EMAIL": _BOT_EMAIL,
        "GIT_COMMITTER_DATE": date,
    }
    return _git(
        repo_root,
        "commit-tree",
        tree_sha,
        "-p",
        parent_sha,
        "-m",
        message,
        env=env,
    ).stdout.strip()


def _github_auth_env(token: str) -> dict[str, str]:
    """Env vars injecting the GitHub auth header without touching .git/config.

    Same `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0`/`GIT_CONFIG_VALUE_0` mechanism
    as `scripts/publish_snapshot.sh` (git >=2.31), scoped to
    `https://github.com/` requests only.
    """
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
    }


def push_sync_branch(repo_root: Path, push_remote: str, commit_sha: str, sync_branch: str) -> None:
    """Force-push `commit_sha` to `refs/heads/<sync_branch>` on `push_remote`.

    `push_remote`'s credentials (the deploy key behind ``GIT_SSH_COMMAND`` in
    CI) come from the caller's environment — see module docstring.
    """
    _git(repo_root, "push", "--force", push_remote, f"{commit_sha}:refs/heads/{sync_branch}")


def land_fast_forward(repo_root: Path, push_remote: str, commit_sha: str, branch: str) -> None:
    """Push `commit_sha` to `refs/heads/<branch>` on `push_remote` — fast-forward only.

    Deliberately no ``--force``: if `branch` moved since the sync commit was
    built on top of it, the remote rejects the push and this raises instead
    of overwriting whatever landed in between.
    """
    _git(repo_root, "push", push_remote, f"{commit_sha}:refs/heads/{branch}")


# --------------------------------------------------------------------------
# GitHub REST — plain urllib, mirroring
# scripts/purge_github_actions_runs.py's request helper.
# --------------------------------------------------------------------------


def _api_request(
    url: str,
    token: str,
    method: str = "GET",
    payload: dict | None = None,
) -> tuple[int, dict | list]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"message": body.decode("utf-8", errors="replace")}
        return exc.code, parsed


def find_open_sync_pr(
    repo: str,
    owner: str,
    sync_branch: str,
    base_branch: str,
    token: str,
) -> dict | None:
    """Return the open sync-branch PR's JSON, or None if none is open."""
    url = f"{_API_ROOT}/repos/{repo}/pulls?head={owner}:{sync_branch}&base={base_branch}&state=open"
    status, payload = _api_request(url, token)
    if status != 200:
        raise SyncError(f"list PRs failed (HTTP {status}): {payload!r}")
    if not isinstance(payload, list) or not payload:
        return None
    return payload[0]


def create_sync_pr(
    repo: str,
    sync_branch: str,
    base_branch: str,
    title: str,
    body: str,
    token: str,
) -> dict:
    """Open a new PR sync_branch -> base_branch; return its JSON."""
    url = f"{_API_ROOT}/repos/{repo}/pulls"
    status, payload = _api_request(
        url,
        token,
        method="POST",
        # Draft: nobody (and no auto-merge) can merge it through the UI. The
        # PR only carries CI; the commit lands by deploy-key fast-forward, and
        # GitHub marks the PR merged once its head is on the base branch.
        payload={
            "title": title,
            "head": sync_branch,
            "base": base_branch,
            "body": body,
            "draft": True,
        },
    )
    if status not in (200, 201) or not isinstance(payload, dict):
        raise SyncError(f"create PR failed (HTTP {status}): {payload!r}")
    return payload


def update_sync_pr(repo: str, pr_number: int, title: str, body: str, token: str) -> dict:
    """PATCH an existing PR's title/body; return its JSON."""
    url = f"{_API_ROOT}/repos/{repo}/pulls/{pr_number}"
    status, payload = _api_request(
        url,
        token,
        method="PATCH",
        payload={"title": title, "body": body},
    )
    if status != 200 or not isinstance(payload, dict):
        raise SyncError(f"update PR failed (HTTP {status}): {payload!r}")
    return payload


def sync_pr(
    repo: str,
    sync_branch: str,
    base_branch: str,
    subject: str,
    body: str,
    token: str,
) -> dict[str, Any]:
    """Create-or-update the sync PR; return its JSON.

    The PR is the vehicle for the mirror's CI and for visibility — it is
    never merged through GitHub (see module docstring); `land_fast_forward`
    lands its head commit, and GitHub then marks it merged.
    """
    owner = repo.split("/", 1)[0]
    pr_body = (
        "Automated sync of GitLab `main` into this mirror. This PR is "
        "force-updated on every sync run and lands by fast-forward once its "
        "required checks pass — do not push commits to it or merge it by hand.\n\n"
        f"{body}"
    )
    existing = find_open_sync_pr(repo, owner, sync_branch, base_branch, token)
    if existing is None:
        pr = create_sync_pr(repo, sync_branch, base_branch, subject, pr_body, token)
        print(f"publish_sync: opened PR #{pr['number']} ({pr.get('html_url', '')})")
    else:
        pr = update_sync_pr(repo, existing["number"], subject, pr_body, token)
        print(f"publish_sync: updated PR #{pr['number']} ({pr.get('html_url', '')})")
    return pr


def required_checks(repo: str, branch: str, token: str) -> list[str]:
    """Required status-check contexts every ruleset applies to `branch`."""
    status, payload = _api_request(f"{_API_ROOT}/repos/{repo}/rules/branches/{branch}", token)
    if status != 200 or not isinstance(payload, list):
        raise SyncError(f"reading the {branch} rules failed (HTTP {status}): {payload!r}")
    return required_check_contexts(payload)


def commit_check_state(
    repo: str,
    sha: str,
    token: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(check runs, commit statuses) GitHub has recorded for `sha`."""
    status, runs = _api_request(
        f"{_API_ROOT}/repos/{repo}/commits/{sha}/check-runs?per_page=100",
        token,
    )
    if status != 200 or not isinstance(runs, dict):
        raise SyncError(f"listing check runs for {sha} failed (HTTP {status}): {runs!r}")
    status, combined = _api_request(f"{_API_ROOT}/repos/{repo}/commits/{sha}/status", token)
    if status != 200 or not isinstance(combined, dict):
        raise SyncError(f"reading the status of {sha} failed (HTTP {status}): {combined!r}")
    return list(runs.get("check_runs") or []), list(combined.get("statuses") or [])


def wait_for_checks(
    repo: str,
    sha: str,
    contexts: list[str],
    token: str,
    timeout: float,
    interval: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> CheckOutcome:
    """Poll `sha`'s checks until every required context has settled or `timeout` passes."""
    deadline = clock() + timeout
    while True:
        check_runs, statuses = commit_check_state(repo, sha, token)
        outcome = evaluate_checks(contexts, check_runs, statuses)
        if outcome is not None:
            return outcome
        if clock() >= deadline:
            return "timeout"
        sleep(interval)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sync GitLab main into the GitHub mirror as a single, append-only, "
            "anonymous bot commit: pushed to a PR branch, checked by the "
            "mirror's CI, then fast-forwarded onto main."
        ),
    )
    parser.add_argument("--remote", default="github", help="GitHub remote name.")
    parser.add_argument("--branch", default="main", help="GitHub base branch.")
    parser.add_argument(
        "--sync-branch",
        default="sync/gitlab",
        help="Branch to force-push the sync commit to.",
    )
    parser.add_argument(
        "--repo",
        default="Anselmoo/SpectraFit-Core",
        help="owner/repo for the GitHub REST calls.",
    )
    parser.add_argument(
        "--push-remote",
        default="github-push",
        help=(
            "Remote every write goes through (sync-branch push and the "
            "fast-forward landing) — authenticated as the rulesets' only "
            "bypass actor (a deploy key over SSH in CI)."
        ),
    )
    parser.add_argument(
        "--check-timeout",
        type=float,
        default=3600.0,
        help="Seconds to wait for the required checks before leaving the PR open.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print the tree/commit/message; push nothing, call no API.",
    )
    parser.add_argument(
        "--no-pr",
        action="store_true",
        help="Push the sync branch but skip the PR and the landing.",
    )
    parser.add_argument(
        "--no-land",
        action="store_true",
        help="Push the sync branch and open/update the PR, but do not land it.",
    )
    return parser.parse_args(argv)


def _land(args: argparse.Namespace, repo_root: Path, commit_sha: str, token: str) -> int:
    """Wait for the required checks on `commit_sha`, then fast-forward the base branch."""
    contexts = required_checks(args.repo, args.branch, token)
    if not contexts:
        print(
            f"publish_sync: REFUSING to land — no required status check applies to "
            f"{args.repo}@{args.branch}. Add one to the branch ruleset; this script "
            "never lands unguarded. PR left open.",
        )
        return 1
    print(f"publish_sync: waiting for required checks {contexts} on {commit_sha}")
    outcome = wait_for_checks(args.repo, commit_sha, contexts, token, args.check_timeout)
    if outcome == "failure":
        print(f"publish_sync: a required check FAILED on {commit_sha} — not landing, PR left open.")
        return 1
    if outcome == "timeout":
        print(
            f"publish_sync: WARNING — required checks still pending after "
            f"{args.check_timeout:.0f}s; PR left open. The next run rebuilds the "
            "same commit and resumes waiting.",
        )
        return 0
    try:
        land_fast_forward(repo_root, args.push_remote, commit_sha, args.branch)
    except subprocess.CalledProcessError as exc:
        print(
            f"publish_sync: FAILED to fast-forward {args.branch} to {commit_sha} — "
            f"{exc.stderr or exc}\n  (a non-fast-forward rejection means "
            f"{args.branch} moved since the sync commit was built; never forced.)",
        )
        return 1
    print(f"publish_sync: landed {commit_sha} on {args.branch} by fast-forward")
    return 0


def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=repo_root,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def _has_commit(repo_root: Path, sha: str) -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            cwd=repo_root,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def sync_guard(repo_root: Path, remote_ref: str) -> tuple[int, str] | None:
    """Refuse a sync that would lose work: ``(exit code, reason)`` or None to go ahead.

    Both hazards come from the sync commit carrying GitLab ``HEAD``'s tree
    wholesale on top of GitHub ``main``:

    * **Stale pipeline** — GitHub was already synced from a GitLab commit newer
      than ``HEAD`` (an older pipeline finishing late). Syncing would roll
      GitHub back. Clean skip, exit 0.
    * **Pending backport** — GitHub ``main`` has native commits after the sync
      boundary whose patch is not on GitLab ``HEAD`` yet. Syncing would revert
      them on GitHub *and* move the boundary past them, so ``backport:github``
      would never find them again: silent loss. Refused, exit 1, until
      ``backport:github`` has landed them on GitLab.

    Needs full history (``GIT_DEPTH: 0`` in the publish jobs); a sync
    boundary commit missing from the clone is itself a refusal.
    """
    # Lazy: backport_from_github imports this module for SYNC_TRAILER. Run as
    # a script, this module is `__main__`; register it under its own name
    # first so that import reuses it instead of executing the file again.
    sys.modules.setdefault("publish_sync", sys.modules[__name__])
    import backport_from_github as backport  # ty: ignore[unresolved-import]

    boundary = backport.find_sync_boundary(remote_ref)
    if boundary is None:
        return None
    synced = parse_sync_trailer(backport.commit_message(boundary))
    if not synced:
        return None
    head = rev_parse(repo_root, "HEAD")
    if synced != head:
        if not _has_commit(repo_root, synced):
            return (
                1,
                (
                    f"GitHub was last synced from GitLab {synced[:10]}, which this clone "
                    "does not contain — cannot tell whether HEAD is newer (publish jobs "
                    "need GIT_DEPTH: 0). Not syncing."
                ),
            )
        if _is_ancestor(repo_root, head, synced):
            return (
                0,
                (
                    f"stale: GitHub is already synced from GitLab {synced[:10]}, which is "
                    f"newer than this pipeline's {head[:10]}. Nothing to do."
                ),
            )
    pending = backport.filter_already_applied(
        backport.candidates_after_boundary(remote_ref, boundary),
        "HEAD",
        synced,
    )
    if pending:
        listing = "\n".join(f"  - {sha[:10]} {subject}" for sha, subject in pending)
        return (
            1,
            (
                f"{len(pending)} GitHub commit(s) after the sync boundary are not on "
                f"GitLab yet — syncing now would revert them on GitHub and lose them "
                f"for good. Run backport:github and merge its MR first:\n{listing}"
            ),
        )
    return None


def main(argv: list[str] | None = None) -> int:
    """Parse CLI args and run the GitLab -> GitHub sync."""
    args = _parse_args(argv)
    repo_root = Path.cwd()
    token = os.environ.get("GITHUB_TOKEN")

    try:
        fetch_remote(repo_root, args.remote, args.branch, token)
    except subprocess.CalledProcessError as exc:
        print(
            f"publish_sync: FAILED to fetch {args.remote}/{args.branch} — {exc.stderr or exc}",
        )
        return 1

    remote_ref = f"{args.remote}/{args.branch}"
    try:
        parent_sha = rev_parse(repo_root, remote_ref)
        remote_tree = rev_parse(repo_root, f"{remote_ref}^{{tree}}")
        filtered_tree = build_filtered_tree(repo_root, "HEAD")
        head_sha = rev_parse(repo_root, "HEAD")
        head_date = commit_date(repo_root, "HEAD")
    except subprocess.CalledProcessError as exc:
        print(f"publish_sync: FAILED to build the filtered tree — {exc.stderr or exc}")
        return 1

    if not sync_needed(filtered_tree, remote_tree):
        print("publish_sync: up to date")
        return 0

    # Only a sync that would actually happen can lose work: guard after the
    # up-to-date check, so a no-op pipeline stays a quiet "up to date".
    try:
        refusal = sync_guard(repo_root, remote_ref)
    except subprocess.CalledProcessError as exc:
        print(f"publish_sync: FAILED to check the sync boundary — {exc.stderr or exc}")
        return 1
    if refusal is not None:
        code, reason = refusal
        print(f"publish_sync: {'REFUSED' if code else 'skipped'} — {reason}")
        return code

    subject, body = build_sync_message(head_sha)
    message = f"{subject}\n\n{body}"

    if args.dry_run:
        print("publish_sync: DRY RUN — nothing pushed, no API calls made.")
        print(f"  filtered tree:        {filtered_tree}")
        print(f"  parent ({remote_ref}): {parent_sha}")
        print(f"  message:\n{message}\n")
        return 0

    try:
        commit_sha = commit_sync_tree(
            repo_root,
            filtered_tree,
            parent_sha,
            subject,
            body,
            head_date,
        )
    except subprocess.CalledProcessError as exc:
        print(f"publish_sync: FAILED to build the sync commit — {exc.stderr or exc}")
        return 1
    print(f"publish_sync: built sync commit {commit_sha}")

    if not token:
        print("publish_sync: FAILED — GITHUB_TOKEN is not set in the environment.")
        return 1

    try:
        push_sync_branch(repo_root, args.push_remote, commit_sha, args.sync_branch)
    except subprocess.CalledProcessError as exc:
        print(f"publish_sync: FAILED to push the sync branch — {exc.stderr or exc}")
        return 1
    print(f"publish_sync: pushed {commit_sha} to {args.push_remote}/{args.sync_branch}")

    if args.no_pr:
        print("publish_sync: --no-pr set — skipping the PR and the landing.")
        return 0

    try:
        sync_pr(args.repo, args.sync_branch, args.branch, subject, body, token)
        if args.no_land:
            print("publish_sync: --no-land set — PR left open.")
            return 0
        return _land(args, repo_root, commit_sha, token)
    except SyncError as exc:
        print(f"publish_sync: FAILED — {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
