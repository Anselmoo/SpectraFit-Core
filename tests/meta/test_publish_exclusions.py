"""Tests for scripts/publish_exclusions.py — the single source of truth for
paths excluded from every GitHub sneak-preview publish (both the exclusion-
removal step and the fast-lane diff-gate consult this same list)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from publish_exclusions import (  # ty: ignore[unresolved-import]
    EXCLUDE_PATTERNS,
    filter_excluded,
    is_excluded,
)


def test_exclude_patterns_match_known_paths() -> None:
    known_excluded = [
        "docs/superpowers/plans/2026-07-01-something.md",
        "docs/superpowers/specs/2026-07-11-github-publish-fast-lane-design.md",
        "docs/superpowers/ledgers/2026-07-01-ledger.md",
        ".claude/audit/2026-07-01.jsonl",
        "DECISIONS.md",
        "DECISIONS-archive.md",
        ".claude/docs/migration-github-to-claude.md",
        "docs/audit-2026-07-02-three-language-audit.md",
        "docs/cycle11-backend-card-before.png",
        "manuscript/draft/outline.md",
        "manuscript/_archive/jors-2026-08/readiness/PUBLICATION_READINESS.md",
        "manuscript/_archive/jors-2026-08/review/MANUSCRIPT-reviewed-2026-08-15.docx",
        "ADR-INDEX.md",
    ]
    for path in known_excluded:
        assert is_excluded(path), f"expected {path!r} to be excluded"


def test_non_excluded_paths_are_not_matched() -> None:
    not_excluded = [
        ".github/workflows/ci.yml",
        "python/spectrafit_core/fit.py",
        "scripts/publish_exclusions.py",
        "docs/superpowers/README.md",
        ".claude/audit.jsonl",
        # The paper's reproducible artifacts: cited by the metapaper's
        # data-availability statement, so they must reach the public mirror.
        "manuscript/examples/fecl4/FeCl4_d5.txt",
        "manuscript/examples/figures/fig_architecture.py",
    ]
    for path in not_excluded:
        assert not is_excluded(path), f"did not expect {path!r} to be excluded"


def test_filter_excluded_removes_only_matching_paths() -> None:
    paths = [
        ".github/workflows/ci.yml",
        "DECISIONS.md",
        "docs/superpowers/plans/x.md",
        "pyproject.toml",
    ]
    result = filter_excluded(paths)
    assert result == [".github/workflows/ci.yml", "pyproject.toml"]


def test_exclude_patterns_is_a_tuple_of_twenty_known_globs() -> None:
    """Pin the exclusion set exactly — an accidental addition silently changes
    what reaches the public GitHub mirror.

    This list is an ALLOWLIST OF PATHS TO STRIP: anything absent from it ships
    publicly. That asymmetry is why the set is pinned rather than merely
    smoke-tested — a wrong *addition* is cosmetic, a wrong *omission* publishes
    something private.

    History, deliberately kept: was eight until `analysis/*` (080112a), then
    eleven on 2026-08-02 when superpowers artifacts moved out of the published
    Zensical tree into top-level `.superpowers/`. `superpowers/*` (undotted) is
    listed alongside it — unused today, but the bare form would otherwise be a
    silent publish the moment anyone created it. Thirteen on 2026-08-08:
    `DECISIONS-archive.md` (an exact-match pattern does not follow a rename —
    `DECISIONS.md` becoming `DECISIONS-archive.md` needed its own new entry,
    caught the same day it happened) and `manuscript/*` (a new private
    top-level working directory). Fourteen on 2026-08-13: that blanket
    `manuscript/*` split into `manuscript/draft/*` + `manuscript/readiness/*`.
    The writing is private; `manuscript/examples/*` — the measured spectra and
    the figure scripts — must ship, because the paper's data-availability
    statement sends readers to the public repository for exactly those files
    and the blanket rule made that statement false on the mirror. Naming the
    private subdirectories keeps this an unambiguous deny-list instead of a
    strip-everything rule with exceptions carved back out; the accepted cost is
    that a NEW manuscript/ subdirectory ships by default.

    That warning came true a third time on 2026-08-21:
    ``manuscript/literature/*`` — a literature-search cache whose
    ``.run/fanout.json`` embeds the author's personal email in every cached
    query URL (``mailto=`` is how Crossref and OpenAlex identify a
    polite-pool caller) — had been publishing to the public mirror since it
    was created. Found by a housekeeping audit, not by this test, because
    this test pins the patterns that EXIST rather than asking whether a new
    directory needs one.

    Seventeen on 2026-08-15, and that accepted cost came due exactly as written:
    `manuscript/review/*` (the reviewer panel's report carrying the author's own
    inline replies) and `manuscript/author-check/*` (the author's open questions
    about their own work) were created after the split and shipped by default
    from that moment. `manuscript/ADR-INDEX.md` is named individually because it
    sits at manuscript/ root and summarises the unpublished decision records.
    Caught before anything was pushed.

    Twenty on 2026-08-21, from a housekeeping audit, for two different reasons.
    ``manuscript/_archive/*`` is the fourth new manuscript/ subdirectory to need
    an entry: the JORS submission was abandoned, so its venue-dead
    correspondence (both annotated `.docx` copies, the round-2 comment archive,
    the generated readiness audit) moved out of review/, readiness/ and
    review-2/ into `manuscript/_archive/jors-2026-08/`.
    `manuscript/assets/jors-template.docx` stayed put and still ships, because
    `render_manuscript.py` hard-errors without it on every `--docx` render.
    And ``manuscript/ADR-INDEX.md`` became ``ADR-INDEX.md``: the file indexes
    DECISIONS-archive.md's ADRs rather than the manuscript, so it moved to the
    repository root to outlive manuscript/. The old exact-match pattern was
    REPLACED, not kept beside it — a literal pattern does not follow a rename,
    the same trap DECISIONS.md -> DECISIONS-archive.md sprang on 2026-08-08.

    The `docs/superpowers/*` entries are retained even though that directory no
    longer exists: they cost nothing and keep the guard in place if a future
    skill default recreates it. `.claude/skills/semantic-debugging` was
    retargeted to `.superpowers/ledgers/` in the same change, along with
    `.claude/hooks/guard-ledger-freshness.sh`'s `LEDGER_DIR` — if those two ever
    disagree, the reaper scans an empty directory and reports success forever.
    """
    assert EXCLUDE_PATTERNS == (
        "docs/superpowers/plans/*",
        "docs/superpowers/specs/*",
        "docs/superpowers/ledgers/*",
        ".claude/audit/*.jsonl",
        "DECISIONS.md",
        "DECISIONS-archive.md",
        ".claude/docs/*",
        "docs/audit-2026-07-02-*.md",
        "docs/cycle11-backend-card-*.png",
        "analysis/*",
        ".superpowers/*",
        "superpowers/*",
        "manuscript/draft/*",
        "manuscript/readiness/*",
        "manuscript/review/*",
        "manuscript/author-check/*",
        "manuscript/review-2/*",
        "manuscript/literature/*",
        "manuscript/_archive/*",
        "ADR-INDEX.md",
    )
