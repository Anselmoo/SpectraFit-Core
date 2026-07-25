#!/usr/bin/env python3
"""Flag GitHub-only branches that have sat un-backported past an age threshold.

Closes the residual mirror-risk self-assess-ci-topology flagged: GitLab is the
documented primary (see CONTRIBUTING.md "Git remotes"), and the GitHub mirror
is a one-directional --force-push snapshot of `main` plus a sanctioned
"Fast iteration on GitHub" lane where a contributor pushes a feature branch
straight to the `github` remote. `scripts/backport_from_github.py` can check
one named branch, but nothing previously scanned the mirror's *entire* branch
list to catch feature-branch work that was iterated on and then forgotten —
this script does that, read-only, informational (never blocking; see
`--strict`).

Deliberately scoped to "list, don't act": like backport_from_github.py, this
never merges, deletes, or pushes anything — only a human decides what to do
with a stale branch (land it via the backport recipe, or delete it).
"""

from __future__ import annotations

import argparse
import subprocess
import time


def _run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout


def ensure_remote(remote_name: str, remote_url: str) -> None:
    """Ensure `remote_name` exists locally (idempotent) — no fetch needed for ls-remote."""
    existing = subprocess.run(
        ["git", "remote"], capture_output=True, text=True, check=True
    ).stdout.split()
    if remote_name not in existing:
        subprocess.run(["git", "remote", "add", remote_name, remote_url], check=True)


def list_remote_branches(remote_name: str) -> list[str]:
    """Return every branch name on `remote_name` (queries the remote directly)."""
    output = _run("git", "ls-remote", "--heads", remote_name)
    branches: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        _, _, ref = line.partition("\t")
        branches.append(ref.removeprefix("refs/heads/"))
    return branches


def commits_ahead(remote_name: str, branch: str, local_ref: str) -> list[str]:
    """SHAs reachable from `remote_name/branch` but not from `local_ref`."""
    subprocess.run(
        ["git", "fetch", remote_name, branch], check=True, capture_output=True
    )
    output = _run(
        "git", "log", f"{local_ref}..{remote_name}/{branch}", "--pretty=format:%H"
    )
    return [line for line in output.splitlines() if line.strip()]


def newest_commit_age_days(remote_name: str, branch: str) -> float:
    """Age in days of the most recent commit on `remote_name/branch`."""
    timestamp = int(
        _run("git", "log", "-1", "--format=%ct", f"{remote_name}/{branch}").strip()
    )
    return (time.time() - timestamp) / 86400.0


def main() -> int:
    """Parse CLI args, scan the GitHub mirror's branches, and report stale ones."""
    parser = argparse.ArgumentParser(
        description=(
            "List GitHub-mirror branches with commits not on local GitLab main, "
            "past an age threshold — surfaces un-backported work before it's lost."
        )
    )
    parser.add_argument("--remote-name", default="github")
    parser.add_argument(
        "--remote-url", default="https://github.com/Anselmoo/spectrafit-core.git"
    )
    parser.add_argument(
        "--local-ref", default="main", help="local branch to diff against"
    )
    parser.add_argument(
        "--min-age-days",
        type=float,
        default=14.0,
        help="only flag branches whose newest commit is at least this old (default 14)",
    )
    parser.add_argument(
        "--skip-branch",
        action="append",
        default=["main"],
        help="branch name to exclude from the scan (repeatable; default excludes 'main', "
        "which is handled by the force-push publish job, not the backport recipe)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 if any stale branch is found (default: informational, always exit 0)",
    )
    args = parser.parse_args()

    try:
        ensure_remote(args.remote_name, args.remote_url)
        branches = list_remote_branches(args.remote_name)
    except subprocess.CalledProcessError as exc:
        print(
            f"check_stale_github_branches: FAILED to list branches — {exc.stderr or exc}"
        )
        return 1

    candidates = [b for b in branches if b not in args.skip_branch]
    stale: list[tuple[str, int, float]] = []
    for branch in candidates:
        try:
            ahead = commits_ahead(args.remote_name, branch, args.local_ref)
            if not ahead:
                continue
            age_days = newest_commit_age_days(args.remote_name, branch)
        except subprocess.CalledProcessError as exc:
            print(
                f"check_stale_github_branches: skipping {branch!r} — {exc.stderr or exc}"
            )
            continue
        if age_days >= args.min_age_days:
            stale.append((branch, len(ahead), age_days))

    if not stale:
        print(
            f"check_stale_github_branches: no branch on {args.remote_name} has "
            f"un-backported commits older than {args.min_age_days:g} day(s)."
        )
        return 0

    print(
        f"check_stale_github_branches: {len(stale)} branch(es) on {args.remote_name} "
        f"have un-backported commits older than {args.min_age_days:g} day(s):"
    )
    for branch, n_commits, age_days in sorted(stale, key=lambda t: -t[2]):
        print(f"  {branch}: {n_commits} commit(s), newest is {age_days:.1f} day(s) old")
    print()
    print("Review each with:  uv run poe backport_github <branch>")

    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
