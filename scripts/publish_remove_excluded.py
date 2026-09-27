#!/usr/bin/env python3
"""Remove non-published paths from the working tree before snapshotting.

Extracted from the inline ``python3 -c "..."`` block that used to live in
``publish:github``'s script (.gitlab/70-publish.yml). Runs BEFORE rrt's
``git publish-snapshot`` ever creates its internal ``git checkout --orphan``
branch — on that orphan branch there is no HEAD commit yet, so git's "does
this match HEAD" safety check trivially fails for every file and rrt's own
``git rm -r --ignore-unmatch`` (used by its ``--exclude`` flag) refuses due to
a missing ``-f``/--force (a repo-release-tools 1.11.2 bug). Removing the
non-published paths here, on the real ``main`` checkout,
sidesteps the bug entirely.

Used by the manual ``publish:github:reset`` job via
``scripts/publish_snapshot.sh``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish_exclusions import is_excluded


def main() -> int:
    """Remove every tracked path outside the public publish scope."""
    tracked = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    to_remove = [path for path in tracked if is_excluded(path)]
    if to_remove:
        subprocess.run(
            ["git", "rm", "-r", "-f", "--ignore-unmatch", "--", *to_remove],
            check=True,
        )
        print(f"Removed {len(to_remove)} non-published path(s) before snapshotting.")
    else:
        print("Every tracked path is published — nothing to remove.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
