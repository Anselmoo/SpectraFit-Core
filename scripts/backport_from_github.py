#!/usr/bin/env python3
"""List commits on a GitHub branch not yet present on the local (GitLab-tracked) main.

Helper for the GitHub-mirror-to-GitLab back-merge recipe — see
docs/superpowers/specs/2026-07-12-github-mirror-backport-recipe.md. Deliberately scoped to
"fetch + list" only: it does NOT cherry-pick, merge, test, or republish. Those steps need a
human's judgment (does the change actually work merged into GitLab's fuller history?) that
this script must not remove.

Two supported modes, both read-only against GitLab:
  1. Default (--github-branch main): direct-edit-in-transit commits made straight on the
     GitHub mirror since the last GitLab->GitHub snapshot publish.
  2. Named branch (--github-branch <feature>): a feature branch developed primarily on
     GitHub (fast-iteration lane — see CONTRIBUTING.md "Fast iteration on GitHub") that's
     ready to land on GitLab as a normal MR.
"""

from __future__ import annotations

import argparse
import subprocess


def _run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout


def fetch_github_remote(remote_name: str, remote_url: str, branch: str) -> None:
    """Ensure `remote_name` exists (idempotent) and fetch `branch`."""
    existing = subprocess.run(
        ["git", "remote"], capture_output=True, text=True, check=True
    ).stdout.split()
    if remote_name not in existing:
        subprocess.run(["git", "remote", "add", remote_name, remote_url], check=True)
    subprocess.run(["git", "fetch", remote_name, branch], check=True)


def commits_only_on_github(remote_ref: str, local_ref: str) -> list[tuple[str, str]]:
    """Return (sha, subject) for every commit reachable from remote_ref but not local_ref."""
    output = _run(
        "git", "log", f"{local_ref}..{remote_ref}", "--pretty=format:%H%x09%s"
    )
    commits: list[tuple[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        sha, _, subject = line.partition("\t")
        commits.append((sha, subject))
    return commits


def main() -> int:
    """Parse CLI args and print the commits pending backport."""
    parser = argparse.ArgumentParser(
        description=(
            "List commits on a GitHub branch not yet on the local GitLab-tracked main."
        )
    )
    parser.add_argument("--remote-name", default="github")
    parser.add_argument(
        "--remote-url", default="https://github.com/Anselmoo/spectrafit-core.git"
    )
    parser.add_argument(
        "--github-branch",
        default="main",
        help=(
            "GitHub branch to check. Default 'main' covers the direct-edit-in-transit "
            "case; pass a feature-branch name for the GitHub-first iteration lane."
        ),
    )
    parser.add_argument(
        "--local-ref", default="main", help="local branch to diff against"
    )
    parser.add_argument(
        "--squash",
        action="store_true",
        help=(
            "Suggest a single squash-merge commit instead of a per-SHA cherry-pick "
            "list — use for a WIP-heavy feature branch where replaying every commit "
            "individually isn't wanted."
        ),
    )
    args = parser.parse_args()

    try:
        fetch_github_remote(args.remote_name, args.remote_url, args.github_branch)
    except subprocess.CalledProcessError as exc:
        print(f"backport_from_github: FAILED to fetch — {exc.stderr or exc}")
        return 1

    remote_ref = f"{args.remote_name}/{args.github_branch}"
    commits = commits_only_on_github(remote_ref, args.local_ref)
    if not commits:
        print(
            f"backport_from_github: no commits on {remote_ref} beyond {args.local_ref}."
        )
        return 0

    print(
        f"backport_from_github: {len(commits)} commit(s) on {remote_ref} pending review:"
    )
    for sha, subject in commits:
        print(f"  {sha[:10]}  {subject}")
    print()
    if args.squash:
        print("Review the commits above, then squash-merge onto a feature branch:")
        print(f"  git checkout -b backport/<description> {args.local_ref}")
        print(f"  git merge --squash {remote_ref}")
        print("  git commit")
    else:
        print("Review each, then cherry-pick the ones you want onto a feature branch:")
        print(f"  git checkout -b backport/<description> {args.local_ref}")
        print(f"  git cherry-pick {' '.join(sha[:10] for sha, _ in commits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
