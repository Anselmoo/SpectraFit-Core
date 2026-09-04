"""Render ``docs/references.md``, the bibliography Zensical does not provide.

The worklist entry this closes tried a different design first:
``docs/includes/references.md``, carrying footnote *definitions*
(``[^key]: ...``) and auto-appended site-wide the way
``docs/includes/abbreviations.txt`` already is (see ``auto_append`` in
``zensical.toml``). That was built and checked against the live site, not
assumed, and it is refuted: `pymdownx.footnotes` renders an unreferenced
footnote *definition* as a visible numbered footnote block, with its full
text, at the bottom of every page that has no ``[^key]`` back-reference —
confirmed on the homepage, the quickstart, and the glossary. Site-wide
auto-append would put a 15-entry bibliography under all ~55 pages, not a
reference page reachable from Reference nav.

The design here is a generated page instead, one entry per reference with a
stable, explicit anchor (``{ #ref-<key> }``) so prose anywhere in the docs
can link ``references.md#ref-<key>`` without depending on heading-slug
auto-generation. It parses ``manuscript/draft/references.ris`` — the same
RIS library ``manuscript/render_manuscript.py``'s ``render_ris`` writes from
the manuscript's own structured CSL data — rather than hand-duplicating
citation text: the manuscript is the source of truth, and a citation edited
there should not silently diverge from what the docs show.

Provenance is absolute: every field rendered here is copied verbatim from
the RIS record. Nothing is completed, corrected, or inferred from outside
knowledge, even for a record this parser can see is incomplete (e.g.
``nist-strd``, ``perez2011``, ``harris2020`` carry only a freeform ``TI`` and
an ``N1`` note reading "No DOI: fields not resolved from a registry; complete
by hand." — that note is reported by :func:`main`, not resolved by it).

Written, like ``docs/tags.md`` and ``docs/performance/index.md``, in full on
every build and gitignored — a generated page cannot go stale in git, only
in a build.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

DOCS = Path(__file__).resolve().parent
RIS_PATH = DOCS.parent / "manuscript" / "draft" / "references.ris"
OUT = DOCS / "references.md"

# RIS tag lines look like "AU  - Newville, M." — a two-character tag, two
# spaces, a dash, a space, then the value (which may be empty, as in one of
# scipy's blank `AU  - ` co-author placeholder lines in the source file).
TAG_LINE = re.compile(r"^([A-Z0-9]{2})  - ?(.*)$")
END_TAG = "ER"

# Tags that legitimately repeat within one record (RIS allows multiple
# authors as repeated AU lines); every other tag is single-valued and a
# repeat is a malformed record, not a second author.
REPEATABLE_TAGS = frozenset({"AU"})


class MalformedRisError(ValueError):
    """Raised for a structurally broken RIS record — never a merely incomplete one.

    Incomplete (a record missing optional fields like ``DO`` or ``JO``) is
    expected and handled by rendering only what is present. Malformed (an
    unparseable line, a record with no ``ID``/``TY``/``TI``, a duplicate
    ``ID``, or a record never closed by ``ER``) is a build failure: silently
    dropping or half-rendering such a record would ship a partial
    bibliography with no signal that anything was wrong.
    """


@dataclass
class Reference:
    """One parsed RIS record, holding only tags actually present in the file."""

    key: str
    kind: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: str | None = None
    journal: str | None = None
    publisher: str | None = None
    doi: str | None = None
    url: str | None = None
    note: str | None = None

    @property
    def venue(self) -> str | None:
        """Return the journal if the RIS carries one, else the publisher, else None.

        Never both, and never a fabricated venue: a `COMP` (software) record
        like ``lmfit`` carries `PB` (Zenodo) but no `JO`; a `JOUR` record
        carries `JO`. Preferring `JO` when both exist matches how every
        `JOUR` record in this file is actually populated (a publisher is
        present too, e.g. "American Chemical Society (ACS)", but the journal
        name is the citation-relevant venue).
        """
        return self.journal or self.publisher


def _split_records(text: str) -> list[list[str]]:
    """Split RIS text into raw line-groups, one per record, on the `ER` tag.

    Raises :class:`MalformedRisError` if content follows the last `ER` (an
    unterminated trailing record) or the file is empty.
    """
    lines = text.splitlines()
    records: list[list[str]] = []
    current: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue
        match = TAG_LINE.match(line)
        if match is None:
            msg = f"unparseable RIS line (not a TAG  - value line and not blank): {line!r}"
            raise MalformedRisError(msg)
        current.append(line)
        if match.group(1) == END_TAG:
            records.append(current)
            current = []
    if current:
        msg = f"RIS file ends mid-record — last record has no closing `ER` tag: {current!r}"
        raise MalformedRisError(msg)
    if not records:
        msg = f"no RIS records found in {RIS_PATH}"
        raise MalformedRisError(msg)
    return records


def _parse_record(lines: list[str]) -> Reference:
    """Parse one record's raw lines into a :class:`Reference`.

    Every required field's absence raises :class:`MalformedRisError` naming
    the record; every optional field's absence is simply left ``None`` (or
    an empty list for authors) and rendered as "not in the RIS entry" further
    down — that is the incomplete-but-not-malformed case the task calls out
    by name for `nist-strd`, `perez2011`, and `harris2020`.
    """
    tags: dict[str, list[str]] = {}
    for line in lines:
        match = TAG_LINE.match(line)
        assert match is not None  # already validated by _split_records
        tag, value = match.group(1), match.group(2).strip()
        if tag == END_TAG:
            continue
        if tag in tags and tag not in REPEATABLE_TAGS:
            msg = f"tag {tag!r} repeated in a record that is not AU: {lines!r}"
            raise MalformedRisError(msg)
        tags.setdefault(tag, []).append(value)

    key = tags.get("ID", [None])[0]
    if not key:
        msg = f"record has no ID tag, cannot anchor it: {lines!r}"
        raise MalformedRisError(msg)
    kind = tags.get("TY", [None])[0]
    if not kind:
        msg = f"record {key!r} has no TY tag"
        raise MalformedRisError(msg)
    title = tags.get("TI", [None])[0]
    if not title:
        msg = f"record {key!r} has no TI (title) tag"
        raise MalformedRisError(msg)

    authors = [a for a in tags.get("AU", []) if a]  # drop blank AU placeholder lines
    doi = tags.get("DO", [None])[0] or None
    url = tags.get("UR", [None])[0] or None

    return Reference(
        key=key,
        kind=kind,
        title=title,
        authors=authors,
        year=tags.get("PY", [None])[0] or None,
        journal=tags.get("JO", [None])[0] or None,
        publisher=tags.get("PB", [None])[0] or None,
        doi=doi,
        url=url,
        note=tags.get("N1", [None])[0] or None,
    )


def parse(text: str) -> list[Reference]:
    """Parse the full RIS text into an ordered list of references.

    Raises :class:`MalformedRisError` (record-structure problems) or a plain
    ``ValueError`` (a duplicate ``ID`` across two otherwise-valid records —
    a build-breaking anchor collision, not a per-record parse failure).
    Order is the RIS file's own order; nothing here re-sorts it.
    """
    references = [_parse_record(record) for record in _split_records(text)]
    seen: set[str] = set()
    for ref in references:
        if ref.key in seen:
            msg = f"duplicate RIS ID {ref.key!r} — anchors would collide"
            raise ValueError(msg)
        seen.add(ref.key)
    return references


def anchor(key: str) -> str:
    """Return the stable anchor id for a reference key: ``ref-<key>``.

    RIS `ID` values in this file are already lowercase-and-hyphen (e.g.
    ``nist-strd``), but the transform is applied defensively rather than
    assumed, the same posture ``_render_tags.py``'s ``slug()`` takes for tag
    text — a future ID with a space or an underscore should not silently
    produce an anchor that collides with or diverges from this function.
    """
    return "ref-" + re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")


def render_entry(ref: Reference) -> str:
    """Render one reference as a heading plus a single citation line.

    Every visible token traces to one RIS tag: authors from `AU`, year from
    `PY`, title from `TI`, venue from :attr:`Reference.venue` (`JO` or
    `PB`), and the link from `DO` when present, else `UR` when present, else
    omitted. Nothing here adds, corrects, or completes a field the RIS
    record does not carry.
    """
    parts: list[str] = []
    if ref.authors:
        joined = "; ".join(ref.authors)
        # Avoid a doubled "M.." — several RIS `AU` values already end in a
        # period (initials like "Newville, M."), so only append one if the
        # joined string doesn't already carry it.
        parts.append(joined if joined.endswith(".") else joined + ".")
    if ref.year:
        parts.append(f"({ref.year}).")
    parts.append(f"*{ref.title}*.")
    if ref.venue:
        parts.append(f"{ref.venue}.")
    if ref.doi:
        parts.append(f"[{ref.doi}](https://doi.org/{ref.doi})")
    elif ref.url:
        parts.append(f"[{ref.url}]({ref.url})")
    citation = " ".join(parts)
    lines = [f"## {ref.key} {{ #{anchor(ref.key)} }}", "", citation]
    if ref.note:
        # Only ever an RIS-authored editorial note (e.g. the "No DOI: ...
        # complete by hand" markers) — rendered verbatim, not paraphrased,
        # so a reader sees exactly what the manuscript's own bibliography
        # already flags as incomplete.
        lines += ["", f"*Note: {ref.note}*"]
    lines.append("")
    return "\n".join(lines)


def render(references: list[Reference]) -> str:
    """Render the full references page, references in RIS file order."""
    with_doi = sum(1 for r in references if r.doi)
    lines = [
        "---",
        "icon: lucide/library-big",
        (
            "description: The manuscript's bibliography — "
            f"{len(references)} references, {with_doi} with a resolvable DOI."
        ),
        "---",
        "",
        "# References",
        "",
        (
            f"{len(references)} references from the manuscript's bibliography "
            f"(`manuscript/draft/references.ris`), {with_doi} with a resolvable "
            "DOI. Link to a specific entry with `references.md#ref-<key>`."
        ),
        "",
    ]
    lines.extend(render_entry(ref) for ref in references)
    return "\n".join(lines)


def main() -> int:
    """Write the references page from the manuscript's RIS bibliography; return 0.

    Any parse failure is fatal (non-zero exit, message on stderr) rather
    than a partial or placeholder page — the task this script implements is
    explicit that a malformed entry must fail the build loudly, not ship a
    silently incomplete bibliography.
    """
    if not RIS_PATH.exists():
        print(f"[references] ERROR: {RIS_PATH} not found", file=sys.stderr)
        return 1
    text = RIS_PATH.read_text(encoding="utf-8")
    try:
        references = parse(text)
    except (MalformedRisError, ValueError) as exc:
        print(f"[references] ERROR: malformed RIS entry in {RIS_PATH}: {exc}", file=sys.stderr)
        return 1
    OUT.write_text(render(references), encoding="utf-8")
    with_doi = sum(1 for r in references if r.doi)
    print(
        f"[references] wrote {OUT.relative_to(DOCS.parent)} "
        f"({len(references)} references, {with_doi} with a DOI)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
