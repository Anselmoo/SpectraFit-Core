"""Integrity of the manuscript claim ledger in manuscript/draft/manuscript-state.json.

Every claim in that ledger carries typed evidence pointers, and the paper's own
thesis is that its claims are checkable rather than asserted. Nothing checked
the pointers themselves, and they had drifted: six named files that no longer
existed — a dissolved section moved under `_superseded/`, plus two relocated
scripts — and seven more cited line numbers past the end of the file they named,
including a regenerated artifact that had shrunk from 4400 lines to 2612. No
test in the repository could see any of it. A ledger whose pointers are never
resolved is a document, not a gate.

These tests make a dangling pointer, an out-of-range line range, a malformed
`lines` spec, a line range on a directory, a duplicate claim id and an unknown
evidence `type` build failures.

Two deliberate non-goals. Citing a *directory* is legitimate evidence — the NIST
fixtures are cited as `python/oracles/nist_strd`, the workspace as `crates` — so
a pointer only has to resolve to something that exists, and is required to be a
file only when it carries line numbers. And nothing here judges whether the
cited lines *support* the claim: that is a reading task, not a mechanical one.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE = REPO_ROOT / "manuscript" / "draft" / "manuscript-state.json"

# Observed vocabulary, plus `ci-config` which the schema allows. A type outside
# this set is far more likely a typo than a new kind.
KNOWN_EVIDENCE_TYPES = frozenset({"repo", "docs", "manifest", "author", "ci-config"})

# "182" | "193-195" | "91,108" | "11-14,64-72"
LINES_SPEC = re.compile(r"^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$")


def _pointers() -> list[tuple[str, str, dict[str, Any]]]:
    """Return (section_role, claim_id, evidence) for every evidence pointer."""
    state = json.loads(STATE.read_text(encoding="utf-8"))
    return [
        (section.get("role", "?"), claim["id"], evidence)
        for section in state["sections"]
        for claim in section.get("claims", [])
        for evidence in claim.get("evidence", [])
    ]


def _claim_ids() -> list[str]:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    return [claim["id"] for section in state["sections"] for claim in section.get("claims", [])]


def _cited_line_numbers(spec: str) -> list[int]:
    """Every line number named by a `lines` spec, ranges expanded to their bounds."""
    return [int(bound) for part in spec.split(",") for bound in part.split("-")]


def test_state_file_is_present_and_parses() -> None:
    assert STATE.is_file(), f"missing manuscript state: {STATE}"
    assert _pointers(), "manuscript state carries no claim evidence at all"


def test_every_evidence_pointer_resolves() -> None:
    """A pointer must name something that exists — a file or a directory."""
    dangling = [
        f"{claim_id} ({role}) -> {evidence['file']}"
        for role, claim_id, evidence in _pointers()
        if evidence.get("file") and not (REPO_ROOT / evidence["file"]).exists()
    ]
    detail = "\n  ".join(dangling)
    assert not dangling, f"claim evidence names paths that do not exist:\n  {detail}"


def test_directory_pointers_carry_no_line_range() -> None:
    """Citing a directory is fine; citing line 5 of a directory is not."""
    bad = [
        f"{claim_id} ({role}) -> {evidence['file']}:{evidence['lines']}"
        for role, claim_id, evidence in _pointers()
        if evidence.get("file")
        and evidence.get("lines")
        and (REPO_ROOT / evidence["file"]).is_dir()
    ]
    detail = "\n  ".join(bad)
    assert not bad, f"line range given for a directory:\n  {detail}"


def test_every_lines_spec_is_well_formed() -> None:
    malformed = [
        f"{claim_id} ({role}) -> {evidence.get('file')}:{evidence['lines']!r}"
        for role, claim_id, evidence in _pointers()
        if evidence.get("lines") and not LINES_SPEC.fullmatch(str(evidence["lines"]))
    ]
    detail = "\n  ".join(malformed)
    assert not malformed, f"unparseable evidence line specs:\n  {detail}"


def test_every_cited_line_range_is_inside_its_file() -> None:
    """A moved or regenerated file keeps its path valid while invalidating line numbers."""
    out_of_range: list[str] = []
    for role, claim_id, evidence in _pointers():
        spec, target = evidence.get("lines"), evidence.get("file")
        if not spec or not target:
            continue
        path = REPO_ROOT / target
        if not path.is_file():
            continue  # missing paths and directories are covered by the tests above
        if not LINES_SPEC.fullmatch(str(spec)):
            continue  # covered by the well-formed test
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if max(_cited_line_numbers(str(spec))) > line_count:
            out_of_range.append(
                f"{claim_id} ({role}) -> {target}:{spec} but the file has {line_count} lines",
            )
    detail = "\n  ".join(out_of_range)
    assert not out_of_range, f"evidence cites lines past end of file:\n  {detail}"


def test_evidence_types_are_known() -> None:
    unknown = sorted(
        {
            str(evidence.get("type"))
            for _role, _claim_id, evidence in _pointers()
            if evidence.get("type") not in KNOWN_EVIDENCE_TYPES
        },
    )
    assert not unknown, f"unknown evidence type(s) {unknown}; known: {sorted(KNOWN_EVIDENCE_TYPES)}"


def test_claim_ids_are_unique() -> None:
    duplicates = sorted(cid for cid, n in Counter(_claim_ids()).items() if n > 1)
    assert not duplicates, f"duplicate claim ids: {duplicates}"
