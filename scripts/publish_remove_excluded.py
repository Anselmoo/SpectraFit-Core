#!/usr/bin/env python3
"""Remove publish-excluded paths from the working tree before snapshotting.

Extracted from the inline ``python3 -c "..."`` block that used to live in
``publish:github``'s script (.gitlab/70-publish.yml). Runs BEFORE rrt's
``git publish-snapshot`` ever creates its internal ``git checkout --orphan``
branch — on that orphan branch there is no HEAD commit yet, so git's "does
this match HEAD" safety check trivially fails for every file and rrt's own
``git rm -r --ignore-unmatch`` (used by its ``--exclude`` flag) refuses due to
a missing ``-f``/--force (confirmed repo-release-tools 1.11.2 bug,
2026-07-11). Removing the excluded paths here, on the real ``main`` checkout,
sidesteps the bug entirely.

Shared by both ``publish:github`` and ``publish:github:fast`` via
``scripts/publish_snapshot.sh`` so the two jobs cannot drift apart.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish_exclusions import is_excluded  # noqa: E402


def main() -> int:
    """Remove every tracked path matching the shared exclude patterns."""
    tracked = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    all_excluded = [path for path in tracked if is_excluded(path)]
    if all_excluded:
        subprocess.run(
            ["git", "rm", "-r", "-f", "--ignore-unmatch", "--", *all_excluded],
            check=True,
        )
        print(f"Removed {len(all_excluded)} excluded path(s) before snapshotting.")
    else:
        print("No excluded paths matched — nothing to remove.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
