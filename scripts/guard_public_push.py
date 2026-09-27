#!/usr/bin/env python3
"""Pre-push guard: nothing outside the publish scope reaches github.com.

Invariant: nothing pushed to a GitHub remote, neither the pushed tree nor any
commit in the pushed history, carries a path for which
:func:`publish_exclusions.is_excluded` is true. The only sanctioned writer to
the public mirror is the CI sync (``scripts/publish_sync.py`` via the
``publish:github*`` jobs), which builds a filtered tree from the include list.
A developer ``git push github <branch>`` would send the full, unfiltered tree
(``analysis/``, ``.superpowers/``, ...) and bypass that filter entirely; this
hook refuses such a push. Pushes to any other remote (GitLab) are never
inspected.

Two sets of paths are checked for every pushed ref, not just the diff of its
last commit: the full tree of the pushed commit, and every path touched by any
commit the remote does not have yet (``git log <rev> --not --remotes=<remote>``).
The second set matters because a private file added and later deleted is gone
from the tip's tree but still travels with the history.

Two invocation forms are supported:

* **pre-commit** (``stages: [pre-push]``): pre-commit consumes git's stdin and
  exposes the push through ``PRE_COMMIT_REMOTE_NAME``/``PRE_COMMIT_REMOTE_URL``
  and ``PRE_COMMIT_TO_REF``.
  On a first push into an empty remote (the moment a freshly created mirror is
  most exposed) pre-commit sets no ``PRE_COMMIT_TO_REF`` and only
  ``PRE_COMMIT_LOCAL_BRANCH``, so that ref is resolved instead. pre-commit only
  reports the first non-delete ref of a multi-ref push.
* **plain git hook**: ``argv = [remote_name, remote_url]`` and one
  ``<local ref> <local sha> <remote ref> <remote sha>`` line per ref on stdin;
  every ref is checked.

There is deliberately no environment-variable escape hatch. ``--no-verify``
still skips every client-side hook, which is why the mirror repository must
also restrict pushes server-side (see
``docs/contributor-guide/github-mirror-workflow.md``).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish_exclusions import is_excluded

ZERO_SHA = "0" * 40
#: How many offending paths are printed before the list is summarised.
MAX_LISTED = 40


def is_github_url(url: str) -> bool:
    """Return True if ``url`` points at github.com (HTTPS or SSH form)."""
    return "github.com" in url.lower()


def _git_z(*args: str) -> set[str]:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout
    return {path for path in out.split("\0") if path}


def excluded_paths_in(rev: str, remote: str = "") -> list[str]:
    """Return every non-publishable path ``rev`` would send to ``remote``.

    That is the tree of ``rev`` plus every path touched by a commit reachable
    from ``rev`` but from none of ``remote``'s tracking refs (all of history
    when the remote has none yet, e.g. a first push into an empty mirror).
    """
    paths = _git_z("ls-tree", "-r", "-z", "--name-only", rev)
    # --diff-filter=d: a deletion publishes no content, only what a commit adds
    # or changes does.
    history = [
        "log",
        "-z",
        "-m",
        "--no-renames",
        "--diff-filter=d",
        "--name-only",
        "--format=",
        rev,
    ]
    if remote:
        history += ["--not", f"--remotes={remote}"]
    paths |= _git_z(*history)
    return sorted(path for path in paths if is_excluded(path))


def _revs_from_pre_commit() -> list[str]:
    to_ref = os.environ.get("PRE_COMMIT_TO_REF", "")
    if to_ref:
        return [to_ref]
    local_branch = os.environ.get("PRE_COMMIT_LOCAL_BRANCH", "")
    return [local_branch] if local_branch else []


def _revs_from_stdin(stdin: str) -> list[str]:
    revs = []
    for line in stdin.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        local_sha = parts[1]
        if local_sha != ZERO_SHA:  # a delete pushes no tree
            revs.append(local_sha)
    return revs


def _short(rev: str) -> str:
    """Abbreviated commit id for ``rev`` (a SHA or, on a first push, a ref name)."""
    return subprocess.run(
        ["git", "rev-parse", "--short=12", rev],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _report(url: str, rev: str, offenders: list[str]) -> None:
    lines = [
        f"guard_public_push: REFUSING push of {_short(rev)} to {url}",
        f"  it would publish {len(offenders)} path(s) outside the public publish scope",
        "  (scripts/publish_exclusions.py), e.g.:",
    ]
    lines += [f"    {path}" for path in offenders[:MAX_LISTED]]
    if len(offenders) > MAX_LISTED:
        lines.append(f"    ... and {len(offenders) - MAX_LISTED} more")
    lines += [
        "  Only the CI sync may write to the GitHub mirror: merge on GitLab and let",
        "  publish:github (scripts/publish_sync.py) publish the filtered tree.",
    ]
    print("\n".join(lines), file=sys.stderr)


def main(argv: list[str]) -> int:
    """Return 1 if any push destined for github.com would carry a private path."""
    if "PRE_COMMIT_REMOTE_URL" in os.environ:
        remote = os.environ.get("PRE_COMMIT_REMOTE_NAME", "")
        url = os.environ["PRE_COMMIT_REMOTE_URL"]
        revs = _revs_from_pre_commit()
    else:
        remote = argv[0] if argv else ""
        url = argv[1] if len(argv) > 1 else ""
        revs = _revs_from_stdin(sys.stdin.read()) if url else []

    if not is_github_url(url):
        return 0

    status = 0
    for rev in revs:
        offenders = excluded_paths_in(rev, remote)
        if offenders:
            _report(url, rev, offenders)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
