#!/usr/bin/env python3
"""Delete all GitHub Actions workflow-run history for the GitHub sneak-preview mirror.

GitHub Actions workflow runs persist independently of git history — they're tied to
immutable commit SHAs, not branch refs, so force-pushing a fresh squash-snapshot (via
`rrt git publish-snapshot`, see scripts/publish_snapshot.sh) does NOT clear old run pages.
Old run pages keep showing old (now-unreachable) commit messages/SHAs — a gap against the
mirror's anonymity goal: the whole point of squash-publish is to hide the internal
development trail, but stale Action run pages defeat that.

Uses the GitHub REST API directly (stdlib urllib, no `gh` CLI dependency — neither
publish:github nor publish:github:fast has a synced .venv or a gh binary available).

DELETE /repos/{owner}/{repo}/actions/runs/{run_id} requires the token to have the
`Actions: Read and write` fine-grained PAT permission (NOT covered by `Contents: Read and
write`, which is what GITHUB_TOKEN is currently scoped to per .gitlab/70-publish.yml's
header comment — this scope must be added on GitHub before real deletes succeed).

Run AFTER a successful publish-snapshot push (called from scripts/publish_snapshot.sh),
so this cleans up runs against the PREVIOUS snapshot's SHA.

CWE-214 hardening: the token is read from the ``GITHUB_TOKEN`` environment
variable, never a ``--token`` CLI argument — process argument vectors are
visible to any co-resident process via ``ps``/``/proc/<pid>/cmdline`` for the
lifetime of the call, which a CLI flag would expose for no reason.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

_API_ROOT = "https://api.github.com"
_PER_PAGE = 100


class GitHubApiError(Exception):
    """Raised when a GitHub API call fails unexpectedly."""


def _request(url: str, token: str, method: str = "GET") -> tuple[int, dict | list]:
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310 (github API, not user input)
            body = resp.read()
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"message": body.decode("utf-8", errors="replace")}
        return exc.code, parsed


def list_all_run_ids(repo: str, token: str) -> list[int]:
    """Return every workflow run's databaseId for `repo`, paginated."""
    run_ids: list[int] = []
    page = 1
    while True:
        url = f"{_API_ROOT}/repos/{repo}/actions/runs?per_page={_PER_PAGE}&page={page}"
        status, payload = _request(url, token)
        if status != 200:
            raise GitHubApiError(f"list runs failed (HTTP {status}): {payload!r}")
        runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
        if not runs:
            break
        run_ids.extend(run["id"] for run in runs)
        if len(runs) < _PER_PAGE:
            break
        page += 1
    return run_ids


def delete_run(repo: str, token: str, run_id: int) -> bool:
    """Delete one workflow run. Returns True on success (HTTP 204)."""
    url = f"{_API_ROOT}/repos/{repo}/actions/runs/{run_id}"
    status, payload = _request(url, token, method="DELETE")
    if status == 204:
        return True
    print(f"  FAILED to delete run {run_id} (HTTP {status}): {payload!r}")
    return False


def main() -> int:
    """Parse CLI args and purge (or list, if --dry-run) all Actions runs."""
    parser = argparse.ArgumentParser(
        description="Delete all GitHub Actions workflow-run history for a repo."
    )
    parser.add_argument("--repo", default="Anselmoo/spectrafit-core", help="owner/repo")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be deleted without deleting anything (mirrors rrt's --dry-run).",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print(
            "purge_github_actions_runs: FAILED — GITHUB_TOKEN is not set in the "
            "environment (Actions: Read and write scope required).",
            file=sys.stderr,
        )
        return 1

    try:
        run_ids = list_all_run_ids(args.repo, token)
    except GitHubApiError as exc:
        print(f"purge_github_actions_runs: FAILED to list runs — {exc}")
        return 1

    if not run_ids:
        print("purge_github_actions_runs: no workflow runs found — nothing to do.")
        return 0

    if args.dry_run:
        print(
            f"purge_github_actions_runs: DRY RUN — would delete {len(run_ids)} run(s):"
        )
        for run_id in run_ids:
            print(f"  {run_id}")
        return 0

    print(f"purge_github_actions_runs: deleting {len(run_ids)} run(s)...")
    failures = [
        run_id for run_id in run_ids if not delete_run(args.repo, token, run_id)
    ]
    if failures:
        print(f"purge_github_actions_runs: {len(failures)} deletion(s) FAILED.")
        return 1
    print(f"purge_github_actions_runs: deleted {len(run_ids)} run(s) successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
