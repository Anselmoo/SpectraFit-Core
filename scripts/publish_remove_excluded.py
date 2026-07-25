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

# `DECISIONS.md` is required to exist by `[tool.rrt.folders]`'s
# `repo-root-required-files` template (enforced by the `rrt-folder-check`
# pre-commit hook, which runs identically against the public snapshot via
# GitHub's Pre-Commit Check). Fully removing it — as every other excluded
# path is — satisfies "don't publish internal decision detail" but silently
# and permanently fails that hook on every GitHub run (found 2026-07-14: it
# passes locally forever, since the real repo always has DECISIONS.md, and
# only ever fails on the actual squashed snapshot). Stub it instead: keep the
# filename present (satisfies the folder check) with placeholder content
# (satisfies "don't publish internal detail").
_STUB_CONTENT = (
    "# Design Decisions — spectrafit-core\n\n"
    "This file is intentionally not published to the public GitHub mirror — it "
    "contains internal AI-collaboration planning and architecture-decision detail "
    "kept private to the primary GitLab repository. This stub exists only so the "
    "repository's required-file layout check (`rrt folder check`) passes on the "
    "public snapshot.\n"
)


def main() -> int:
    """Remove every tracked path matching the shared exclude patterns.

    `DECISIONS.md` is stubbed rather than removed — see `_STUB_CONTENT` above.
    """
    tracked = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    all_excluded = [path for path in tracked if is_excluded(path)]
    to_remove = [path for path in all_excluded if path != "DECISIONS.md"]
    if to_remove:
        subprocess.run(
            ["git", "rm", "-r", "-f", "--ignore-unmatch", "--", *to_remove],
            check=True,
        )
    if "DECISIONS.md" in all_excluded:
        Path("DECISIONS.md").write_text(_STUB_CONTENT, encoding="utf-8")
        subprocess.run(["git", "add", "--", "DECISIONS.md"], check=True)
    if all_excluded:
        print(
            f"Removed {len(to_remove)} excluded path(s); stubbed DECISIONS.md."
            if "DECISIONS.md" in all_excluded
            else f"Removed {len(to_remove)} excluded path(s) before snapshotting."
        )
    else:
        print("No excluded paths matched — nothing to remove.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
