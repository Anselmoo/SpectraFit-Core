#!/usr/bin/env python3
"""Single source of truth for paths excluded from the GitHub sneak-preview publish.

Consulted from two places, which is exactly why this exists as its own module:

1. ``scripts/publish_remove_excluded.py`` — removes these paths from the real
   ``main`` checkout before ``rrt git publish-snapshot`` ever creates its
   orphan branch (working around a repo-release-tools 1.11.2 bug in its own
   ``--exclude`` handling; see ``.gitlab/70-publish.yml``).
2. ``scripts/fast_lane_gate.py`` — the fast-lane diff-gate excludes these same
   paths before asserting "is everything else under .github/**?", since they
   are expected to always differ between the GitLab and GitHub remotes and
   would otherwise always fail the gate.

Keeping ONE list here means the patterns cannot drift out of sync between the
two call sites. Note: ``pyproject.toml``'s
``[tool.rrt.publish_targets.github].exclude`` TOML array duplicates this list
for documentation purposes only — it is inert (rrt's own ``--exclude`` flag is
deliberately never invoked; see the bug note in ``.gitlab/70-publish.yml``).
This module, not the TOML array, is the actual source of truth at runtime.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable

EXCLUDE_PATTERNS: tuple[str, ...] = (
    "docs/superpowers/plans/*",
    "docs/superpowers/specs/*",
    "docs/superpowers/ledgers/*",
    ".claude/audit/*.jsonl",
    "DECISIONS.md",
    # 2026-08-08: the pre-2026-08-08 decision log, renamed via `git mv` when
    # DECISIONS.md was reset to append-only going forward. Same class as
    # DECISIONS.md above — an exact-match pattern does NOT follow a rename,
    # so this needed its own entry the moment the old file got a new path.
    "DECISIONS-archive.md",
    # Internal Claude/hook-tooling docs relocated out of docs/ (see
    # analysis/andon/ledger-docs-publish/gaps/gap-0-relocate-internal-docs.md) —
    # not spectrafit-core's public API documentation, so excluded even at
    # their new .claude/docs/ path since .claude/ is otherwise published
    # wholesale today.
    ".claude/docs/*",
    # Process ephemera from a specific audit cycle — never actually excluded
    # despite being assumed excluded by an earlier docs-drift scope note.
    "docs/audit-2026-07-02-*.md",
    "docs/cycle11-backend-card-*.png",
    # codebase-consistency / andon working artifacts (PREFLIGHT, scan findings,
    # module×dimension matrix + its HTML viewer, alignment briefs, ledgers).
    # Internal process record of how the codebase got aligned — same class as
    # DECISIONS.md, not public API documentation. Note `fnmatch`'s `*` spans
    # `/`, so this single pattern covers nested paths like
    # `analysis/crates/PREFLIGHT.md` as well.
    "analysis/*",
    # Superpowers working artifacts (brainstorming specs, writing-plans plans,
    # ledgers). Same class as the `docs/superpowers/*` patterns above and
    # `analysis/*`: process record, not public documentation. Tracked on GitLab
    # so design history survives; stripped from the GitHub mirror.
    #
    # NAMING CONVENTION — dot-prefix what WE control, leave tool-owned paths as
    # the tool names them:
    #   `.superpowers/`  canonical, ours. Holds `specs/`, `plans/`, `ledgers/`,
    #                    plus a `.gitkeep` so the directory survives when empty.
    #   `analysis/`      NOT dot-prefixed, and deliberately so: the
    #                    codebase-consistency plugin writes `analysis/<area>/…`
    #                    as a hardcoded path. Renaming it would break every
    #                    future `/consistency-*` invocation. It is also cited
    #                    across DECISIONS.md, tracked docs, and commit messages.
    #   `.claude/docs/`  excluded above, same reasoning.
    #
    # Both `.superpowers/*` and `superpowers/*` are listed. The bare form is not
    # in use today, but this list is an ALLOWLIST OF PATHS TO STRIP — anything
    # absent from it ships to the public GitHub mirror. Carrying the second
    # pattern costs nothing and closes the failure mode where someone creates
    # the non-dotted variant and it silently publishes.
    ".superpowers/*",
    "superpowers/*",
    # manuscript/ (2026-08-08, narrowed 2026-08-13): the WRITING is private,
    # the reproducible artifacts are not. `manuscript/draft/*` (prose in
    # progress) and `manuscript/readiness/*` (a venue-checklist audit) stay
    # stripped; `manuscript/examples/*` — the measured FeCl4 spectra and the
    # figure scripts — deliberately ships, because the paper's data-availability
    # statement points readers at the public repository for exactly those files.
    # Under the previous blanket `manuscript/*` that statement was false on the
    # mirror. Naming the two private subdirectories, rather than stripping the
    # whole tree and carving exceptions back out, keeps the rule an unambiguous
    # deny-list. The trade-off is real and accepted: a NEW manuscript/
    # subdirectory now ships by default, exactly like every other top-level
    # path in this repo.
    # New top-level paths ship by default (this list is an allowlist of what
    # to STRIP), so this needed adding the moment the directory was created,
    # same as every other working-artifact directory above.
    "manuscript/draft/*",
    "manuscript/readiness/*",
    # Added 2026-08-15, and this is the documented trade-off above coming due:
    # `manuscript/review/*` holds the reviewer panel's report WITH the author's
    # own inline replies, and `manuscript/author-check/*` holds the author's
    # open questions about their own work. Both are private working material of
    # exactly the same class as draft/ and readiness/, and both shipped by
    # default from the moment the directories were created.
    "manuscript/review/*",
    "manuscript/author-check/*",
    # Added 2026-08-18, the same trade-off a second time. `manuscript/review-2/*`
    # holds an outside reviewer's panel report, their annotated Word copy with 19
    # anchored comments, and the author's point-by-point response. Private
    # working material of the same class as review/, and it shipped by default
    # from the moment the directory was created. A dated sibling of an already
    # stripped directory is the shape this failure keeps taking: whoever adds
    # review-3/ has to add it here too.
    "manuscript/review-2/*",
    # Added 2026-08-21, the third instance of the very trade-off the comment
    # above warns about: a NEW manuscript/ subdirectory shipped by default
    # because nobody added it here. `manuscript/literature/` is a literature
    # search cache; `.run/fanout.json` embeds the author's personal email in
    # every cached query URL (`mailto=` is how Crossref/OpenAlex identify a
    # polite-pool caller). It was publishing to the public mirror.
    "manuscript/literature/*",
    # Added 2026-08-21 by the housekeeping audit's actions 8 and 10, the fourth
    # instance of the same trade-off. The JORS submission was abandoned, so
    # `manuscript/_archive/jors-2026-08/*` now holds the venue-dead
    # correspondence that used to sit under review/, readiness/ and review-2/:
    # both round-1 annotated `.docx` copies, the round-2 comment archive, and
    # the generated JORS readiness audit. Private working material of exactly
    # the class of the directories it came from — and a NEW manuscript/
    # subdirectory ships by default, so it needs naming here the moment it is
    # created. `manuscript/assets/jors-template.docx` was deliberately NOT
    # archived with them: `render_manuscript.py:697,898` hard-errors without it
    # and re-verifies its sha256 on every `--docx` render, so it is a live
    # dependency rather than correspondence, and it keeps shipping as before.
    "manuscript/_archive/*",
    # Moved 2026-08-21 from `manuscript/ADR-INDEX.md` to the repository root:
    # the file indexes DECISIONS-archive.md's ADRs, not the manuscript, so it
    # should outlive manuscript/. Both decision logs are already stripped above
    # and the index of them is stripped with them. The old path was REPLACED,
    # not kept alongside — an exact-match pattern does not follow a rename, the
    # same failure DECISIONS.md -> DECISIONS-archive.md caused on 2026-08-08.
    "ADR-INDEX.md",
)


def is_excluded(path: str) -> bool:
    """Return True if ``path`` matches any of the shared exclude patterns."""
    return any(fnmatch.fnmatch(path, pattern) for pattern in EXCLUDE_PATTERNS)


def filter_excluded(paths: Iterable[str]) -> list[str]:
    """Return ``paths`` with every excluded entry removed, order preserved."""
    return [path for path in paths if not is_excluded(path)]
