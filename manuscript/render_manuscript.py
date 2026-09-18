#!/usr/bin/env python3
"""Render MANUSCRIPT.md and TODO.md from manuscript-state.json + sections/*.md.

Why this exists as a committed script. The original render was produced by a
drafting tool that was never committed, so `MANUSCRIPT.md` could not be
rebuilt from its own sources — it drifted three revisions behind
`sections/*.md` (wrong title, no case study, unresolved `[CITE:]` markers)
with nothing in the repo able to detect or fix that. For a paper whose subject
is checkable claims, a deliverable that cannot be regenerated from its inputs
is the wrong artefact to be handing a reviewer.

Usage:

    uv run python manuscript/render_manuscript.py            # write
    uv run python manuscript/render_manuscript.py --check    # CI-style diff

`--check` exits non-zero when the rendered output differs from what is on
disk, which is what makes staleness a build failure rather than something
noticed by eye months later.

Section order and headings come from the venue binding in the state file, so
retargeting the paper at a different venue is a state change, not a rewrite of
this script.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DRAFT = HERE / "draft"
STATE = DRAFT / "manuscript-state.json"
SECTIONS = DRAFT / "sections"
ASSETS = HERE / "assets"
JORS_TEMPLATE = ASSETS / "jors-template.docx"
DOCX = DRAFT / "MANUSCRIPT.docx"
MANIFEST = DRAFT / ".render-manifest.json"

# Provenance stamps in MANUSCRIPT.md that move on their own. Neither can ever
# be stable at check time: the timestamp changes every run, and the commit line
# records HEAD at render time, so committing a render always leaves it one
# commit behind by construction. They are still written — a reader wants to
# know which tree produced the file — they are just not evidence of staleness.
PROVENANCE_STAMPS = ("- Generated at:", "- Repository commit:")

# JORS software-metapaper heading order. `role` keys the section files; the
# heading is what the venue calls that role.
MANIFEST_SCHEMA = 3
"""Version of `.render-manifest.json`.

Bumped to 3 when per-figure hashes were added, so `figure_staleness` can tell a
regenerated figure from an unchanged one. A manifest written by an older renderer
carries no hashes and is reported as due for a re-render rather than trusted.
"""


JORS_BINDING: list[tuple[str, str | None]] = [
    ("summary", None),  # the title — rendered as `## Title`, not a heading of its own
    # Author front matter. Both are venue-required and neither is derivable from
    # the repository, so they sit in section files supplied by the author.
    ("authors", "Paper Authors"),
    ("author_roles", "Paper Author Roles and Affiliations"),
    ("abstract", "Abstract"),
    ("context", "Introduction"),
    ("method", "Implementation and architecture"),
    # Quality control carries the empirical evidence as well as the test
    # protocol. It used to be split: a hand-added "Validation" section held the
    # benchmark and certified-value results, on the argument that the venue's
    # Quality control asks for testing levels, environments and a sample
    # input/output rather than for measurements. The first outside reader read
    # the extra top-level section as a format-compliance failure -- the Overview
    # is Introduction / Implementation and architecture / Quality control, and
    # nothing else -- and read its 3,300 words as the paper's centre of gravity
    # sitting outside the paper's shape. The results are compressed inside
    # Quality control now, and the detail is pointed at the live report and the
    # FAIR data package.
    ("evidence", "Quality control"),
    # Both of these are named by their part header below, not by a heading of
    # their own — in the venue's structure the part *is* the section.
    ("availability", None),
    ("reuse", None),
    # End matter, as real sections rather than as a submission-form checklist.
    # These previously lived in one "Submission metadata" section that opened
    # by telling the author which fields to fill in — so the paper carried
    # ADVICE about writing a funding statement instead of a funding statement,
    # and JORS requires the statement itself. The author-only questions moved
    # to manuscript/draft/AUTHOR-CHECKLIST.md, which is deliberately not
    # rendered: a submitted paper carries the answers, not the questions.
    ("acknowledgements", "Acknowledgements"),
    ("funding", "Funding statement"),
    ("competing", "Competing interests"),
    ("data_availability", "Data availability"),
]

# The venue numbers its three top-level parts, and the numbering is load-bearing
# structure rather than decoration: "(2) Availability" and "(3) Reuse potential"
# are the section names, while "(1) Overview" groups everything above them. Each
# is emitted immediately before the role it opens.
JORS_PARTS: dict[str, str] = {
    "summary": "(1) Overview",
    "availability": "(2) Availability",
    "reuse": "(3) Reuse potential",
}

# Rendered in the front matter directly after the abstract, per venue
# convention, rather than in the body flow above.
FRONT_MATTER_AFTER_ABSTRACT: list[tuple[str, str]] = [
    ("keywords", "Keywords"),
]

SEVERITY_ORDER = {"blocker": 0, "should-fix": 1, "informational": 2}


def git_commit() -> str:
    """Return the current HEAD sha, or a marker when git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=HERE,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
    return out.stdout.strip()


def _placeholders(text: str) -> list[str]:
    """Return unresolved ``{{TOKEN}}`` placeholders, in order of appearance."""
    return re.findall(r"\{\{([A-Z0-9_]+)\}\}", text)


def figure_block(fig: dict[str, Any]) -> str:
    """Return the markdown for one figure: the image, then its numbered caption.

    The image carries `alt_text` as its alt attribute and the caption is a
    separate paragraph, so a screen reader gets the short description and the
    page gets the full caption. Folding both into pandoc's implicit-figure
    caption would make them the same string, which serves neither.

    No width is set: pandoc scales an image down to the reference document's
    text width on its own, and a hard-coded width would silently misfit if the
    venue reissues the template with different margins.
    """
    raster = fig["files"]["raster_300dpi"]
    rel = os.path.relpath(HERE.parent / raster, DRAFT)
    alt = fig.get("alt_text", "").replace("[", "(").replace("]", ")")
    return f"![{alt}]({rel})\n\n**Figure {fig['number']}.** {fig['caption']}"


def place_figures(body: str, figures: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Insert each figure after the paragraph that first cites it.

    Anchoring on the prose keeps figure placement a property of the argument
    rather than of the render order, so a figure follows its discussion even
    when sections are reordered by a venue rebinding. A figure the prose never
    cites is returned unplaced rather than dropped or silently parked at the
    end — an uncited figure is a manuscript defect worth surfacing.
    """
    blocks = body.split("\n\n")
    placements: list[tuple[int, str]] = []
    unplaced: list[dict[str, Any]] = []
    for fig in sorted(figures, key=lambda f: f["number"]):
        if not Path(HERE.parent / fig["files"]["raster_300dpi"]).exists():
            msg = f"figure {fig['number']}: missing raster {fig['files']['raster_300dpi']}"
            raise SystemExit(msg)
        pattern = re.compile(rf"\bFigure {fig['number']}\b")
        # Searched against the original blocks, so inserted captions can never
        # become anchors for a later figure.
        idx = next((i for i, b in enumerate(blocks) if pattern.search(b)), None)
        if idx is None:
            unplaced.append(fig)
            continue
        placements.append((idx, figure_block(fig)))
    for idx, block in sorted(placements, key=lambda pair: pair[0], reverse=True):
        blocks.insert(idx + 1, block)
    return "\n\n".join(blocks), unplaced


def check_tables(body: str, tables: list[dict[str, Any]]) -> None:
    """Fail when a registered table has no captioned occurrence *above* it.

    The table markup lives in the section prose while its number lives in the
    state file, so nothing else would notice the two drifting apart.

    Placement is checked as well as existence, and the two directions differ by
    float type: a table carries its title on top, a figure and a listing carry
    theirs underneath. A caption is ordinary prose here, nothing in the renderer
    positions it, so this guard is the only thing holding the convention.
    "Above" means the nearest pipe-table row after the caption is closer than
    the nearest one before it.
    """
    missing, misplaced = [], []
    for table in tables:
        marker = f"**Table {table['number']}.**"
        at = body.find(marker)
        if at < 0:
            missing.append(table["number"])
            continue
        before = body.rfind("\n|", 0, at)
        after = body.find("\n|", at)
        if after < 0 or (before >= 0 and after - at > at - before):
            misplaced.append(table["number"])
    if missing:
        nums = ", ".join(str(n) for n in missing)
        msg = f"registered table(s) with no caption in the manuscript: {nums}"
        raise SystemExit(msg)
    if misplaced:
        nums = ", ".join(str(n) for n in misplaced)
        msg = (
            f"table caption(s) beneath the table rather than above it: {nums}; "
            f"tables carry their title on top, figures and listings underneath"
        )
        raise SystemExit(msg)


# Venue limits the build can enforce, so neither drifts back by accretion. Both
# are the kind of thing a reader notices before an editor does: a 171-word alt
# string is read aloud in full before the caption a screen-reader user is waiting
# for, and a 200-word caption is a second methods section.
ALT_TEXT_WORD_LIMIT = 20
CAPTION_WORD_LIMIT = 100


def check_figure_lengths(figures: list[dict[str, Any]]) -> None:
    """Fail when a figure's alt text or caption exceeds what the venue asks for."""
    problems = [
        f"figure {f['number']} {field} is {len(f.get(field, '').split())} words (limit {limit})"
        for f in figures
        for field, limit in (("alt_text", ALT_TEXT_WORD_LIMIT), ("caption", CAPTION_WORD_LIMIT))
        if len(f.get(field, "").split()) > limit
    ]
    if problems:
        msg = "; ".join(problems)
        raise SystemExit(msg)


def check_algorithms(body: str, algorithms: list[dict[str, Any]], label: str = "Algorithm") -> None:
    """Fail when a registered float has no captioned occurrence in the body.

    `label` selects the caption keyword, so the same guard serves algorithms and
    listings; they are numbered in separate sequences and a listing captioned
    "Algorithm 1" would be as wrong as no caption at all.

    Same guard as `check_tables`, for the same reason: the float is typeset
    outside the render (LaTeX, via the plugin's algorithm2e mode) while its
    number lives in the state file, so nothing else would notice them diverging.

    An algorithm marked `caption_in_image` is exempt, because its caption is set
    inside the float by algorithm2e and a prose copy beneath the image would be
    the same text twice. The exemption is per-algorithm rather than a relaxation
    of the guard: any algorithm without the flag must still carry a caption.
    """
    missing = [
        a["number"]
        for a in algorithms
        if not a.get("caption_in_image") and f"**{label} {a['number']}.**" not in body
    ]
    if missing:
        nums = ", ".join(str(n) for n in missing)
        msg = f"registered {label.lower()}(s) with no caption in the manuscript: {nums}"
        raise SystemExit(msg)


def render_manuscript(state: dict) -> tuple[str, list[str]]:
    """Return the rendered manuscript and every unresolved placeholder in it."""
    lines: list[str] = []
    venue = state["venue"]
    add = lines.append

    add(f"# {state.get('title') or venue['id']}")
    add("")
    add(
        "Generated by `manuscript/render_manuscript.py` from `manuscript-state.json` "
        "and `sections/*.md`. Regenerated in full on every run; edit the section "
        "files, never this one.",
    )
    add("")
    add(f"- Venue: {venue['id']} ({venue['binding']})")
    add(f"- Generated at: {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    add(f"- Repository commit: `{git_commit()}`")
    add("")

    by_role = {s["role"]: s for s in state["sections"]}
    unresolved: list[str] = []

    for role, heading in JORS_BINDING:
        section = by_role.get(role)
        if section is None:
            continue
        body = (DRAFT / section["file"]).read_text().strip()
        if not body:
            continue
        unresolved.extend(f"{role}: {{{{{token}}}}}" for token in _placeholders(body))
        part = JORS_PARTS.get(role)
        if part:
            add(f"# {part}")
            add("")
        if role == "summary":
            add("## Title")
            add("")
            add(body)
            add("")
            continue
        if heading:
            add(f"## {heading}")
            add("")
        add(body)
        add("")
        # Keywords belong immediately after the abstract in the front matter,
        # not in the body flow, so they are emitted here rather than as their
        # own entry in JORS_BINDING.
        if role == "abstract":
            for fm_role, fm_heading in FRONT_MATTER_AFTER_ABSTRACT:
                fm_section = by_role.get(fm_role)
                if fm_section is None:
                    continue
                fm_body = (DRAFT / fm_section["file"]).read_text().strip()
                if not fm_body:
                    continue
                add(f"## {fm_heading}")
                add("")
                add(fm_body)
                add("")

    # Figures are woven into the body at their first citation; only the ones the
    # prose never mentions fall through to a trailing section.
    body, unplaced = place_figures("\n".join(lines), state.get("figures", []))
    check_tables(body, state.get("tables", []))
    check_figure_lengths(state.get("figures", []))
    check_algorithms(body, state.get("algorithms", []))
    # Listings are typeset code, numbered in their own sequence. Same guard, and
    # the same `caption_in_image` exemption, since both floats carry their
    # caption inside the image the way the venue's own algorithm boxes do.
    check_algorithms(body, state.get("listings", []), label="Listing")
    lines = body.split("\n")
    add = lines.append  # `lines` is a new list; rebind or the appends are lost

    if unplaced:
        add("## Figures")
        add("")
        for f in sorted(unplaced, key=lambda x: x["number"]):
            add(figure_block(f))
            if f.get("status") != "rendered":
                add(f"_[{f.get('status')}]_")
            add("")

    refs = state.get("references", [])
    if refs:
        # Vancouver numbers references in order of first appearance. This used to
        # enumerate `state["references"]` in the order that array happened to be
        # written, while claiming citation order in a comment -- so 13 of the 15
        # were misnumbered, and the two that were right included one coincidence.
        # The order is derived from the rendered body instead, which is the only
        # thing that knows where a key first appears.
        #
        # Keys are read out of `[key]` and `[key1, key2]` brackets in the body
        # built so far, before the reference list itself is appended.
        body_so_far = "\n".join(lines)
        first_at: dict[str, int] = {}
        for m in re.finditer(r"\[([a-z][a-z0-9,\- ]*)\]", body_so_far):
            for key in (k.strip() for k in m.group(1).split(",")):
                if key and key not in first_at:
                    first_at[key] = m.start()
        # An uncited reference sorts last, keeping its relative state order, so it
        # is visible at the end of the list rather than silently renumbered into
        # the middle. `poe`-side auditing catches whether it should be there at all.
        ordered = sorted(
            enumerate(refs),
            key=lambda pair: (first_at.get(pair[1]["key"], len(body_so_far)), pair[0]),
        )
        add("## References")
        add("")
        # The section bodies cite by key (`[lmfit]`), so the mapping from key to
        # number is printed alongside — substituting numerals into the prose is a
        # submission-time step against the venue's template, not baked in here.
        for n, (_, r) in enumerate(ordered, start=1):
            add(f"{n}. {r['vancouver']}  _(cited as `[{r['key']}]`)_")
        add("")

    return "\n".join(lines).rstrip() + "\n", unresolved


def render_todo(state: dict, unresolved: list[str]) -> str:
    """Return the TODO list, regenerated from state; it carries no checkbox state."""
    todo = [t for t in state.get("todo", []) if t.get("status") != "resolved"]
    todo.sort(key=lambda t: SEVERITY_ORDER.get(t.get("severity", "informational"), 9))
    counts: dict[str, int] = {}
    for t in todo:
        counts[t.get("severity", "informational")] = (
            counts.get(t.get("severity", "informational"), 0) + 1
        )

    lines = [
        f"# Manuscript TODO — {state['venue']['id']}",
        "",
        "Generated by `manuscript/render_manuscript.py` from `manuscript-state.json`.",
        "",
        (
            "Fully regenerated on every run. It carries no checkbox state: resolve an "
            "item in the state file and its line disappears here."
        ),
        "",
        "Gates: " + " · ".join(f"{k}: {v}" for k, v in state["gates"].items()),
        "",
    ]
    if unresolved:
        lines += [
            (
                f"**{len(unresolved)} unresolved placeholder(s)** in the rendered "
                "manuscript — these are deliberate, and block only the numbers they "
                "stand in for:"
            ),
            "",
            *(f"- `{u}`" for u in unresolved),
            "",
        ]
    summary = " · ".join(f"{n} {sev}" for sev, n in sorted(counts.items()))
    lines += [f"{len(todo)} open item(s)" + (f": {summary}" if summary else ""), ""]
    for t in todo:
        owner = f" ({t['owner']})" if t.get("owner") else ""
        role = f" [{t['role']}]" if t.get("role") else ""
        lines.append(f"- **{t.get('severity', 'informational')}**{role}{owner} {t['text']}")
    return "\n".join(lines).rstrip() + "\n"


# Style ids pandoc writes into `w:pStyle`/`w:tblStyle` that the JORS template
# does not define. Word resolves an unknown id to Normal *silently*, so without
# these the rendered paper opens cleanly with every heading as plain body text --
# and every table as a real Word table with no rules at all, which is what the
# `Table` entry below fixes: three horizontal rules in the scholarly convention
# (top, under the header row, bottom), no vertical lines, header row bold. They are
# `basedOn` the template's own UP styles rather than restating its fonts, so a
# revised template propagates instead of drifting.
PANDOC_STYLE_ALIASES = """
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="UPPaperTitle"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="UPPaperTitle"/><w:uiPriority w:val="9"/><w:qFormat/><w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="UPSectionHeading"/><w:uiPriority w:val="9"/><w:qFormat/><w:pPr><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="1"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="BodyText"><w:name w:val="Body Text"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="120"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="FirstParagraph"><w:name w:val="First Paragraph"/><w:basedOn w:val="BodyText"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Compact"><w:name w:val="Compact"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="0"/><w:contextualSpacing/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="BlockText"><w:name w:val="Block Text"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:ind w:left="720"/><w:spacing w:after="120"/></w:pPr><w:rPr><w:i/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:sz w:val="20"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ImageCaption"><w:name w:val="Image Caption"/><w:basedOn w:val="Caption"/><w:qFormat/></w:style>
<w:style w:type="table" w:styleId="Table"><w:name w:val="Table"/><w:basedOn w:val="TableNormal"/><w:uiPriority w:val="59"/><w:qFormat/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="8" w:space="0" w:color="000000"/><w:bottom w:val="single" w:sz="8" w:space="0" w:color="000000"/></w:tblBorders><w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:bottom w:w="60" w:type="dxa"/><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblStylePr w:type="firstRow"><w:rPr><w:b/></w:rPr><w:tcPr><w:tcBorders><w:bottom w:val="single" w:sz="8" w:space="0" w:color="000000"/></w:tcBorders></w:tcPr></w:tblStylePr></w:style>
<w:style w:type="paragraph" w:styleId="TableCaption"><w:name w:val="Table Caption"/><w:basedOn w:val="Caption"/><w:qFormat/></w:style>
<w:style w:type="character" w:styleId="VerbatimChar"><w:name w:val="Verbatim Char"/><w:basedOn w:val="DefaultParagraphFont"/><w:qFormat/><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/><w:sz w:val="20"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="SourceCode"><w:name w:val="Source Code"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/><w:contextualSpacing/><w:ind w:left="180"/></w:pPr><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/><w:sz w:val="18"/></w:rPr></w:style>
<w:style w:type="character" w:styleId="FootnoteReference"><w:name w:val="footnote reference"/><w:basedOn w:val="DefaultParagraphFont"/><w:qFormat/><w:rPr><w:vertAlign w:val="superscript"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="FootnoteText"><w:name w:val="footnote text"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="0"/></w:pPr><w:rPr><w:sz w:val="18"/></w:rPr></w:style>
"""


def submission_markdown(md: str) -> str:
    """Strip from MANUSCRIPT.md what belongs to the repo but not to a reviewer.

    Two things are dropped. The provenance preamble (how the file was built,
    which commit, when) documents the render, not the science — the previous
    docx carried it as its opening paragraph. And `## Title` restates the H1
    verbatim, which reads as a duplicated heading once Word applies the
    template's title style.
    """
    md = re.sub(
        r"^Generated by `manuscript/render_manuscript\.py`.*?\n\n",
        "",
        md,
        count=1,
        flags=re.DOTALL | re.MULTILINE,
    )
    md = re.sub(r"^- (?:Venue|Generated at|Repository commit):.*\n", "", md, flags=re.MULTILINE)
    md = re.sub(r"## Title\n\n.*?\n\n(?=#)", "", md, count=1, flags=re.DOTALL)
    md = vancouver_numerals(md)
    md = footnotes_to_endnotes(md)
    return re.sub(r"\n{3,}", "\n\n", md)


CITE_RE = re.compile(r"\[([a-z][a-z0-9,\- ]*)\]")


def vancouver_numerals(md: str) -> str:
    """Replace `[key]` citations with the venue's `(1)`, `(2)` numerals.

    The section bodies cite by key because a key survives an edit that moves a
    paragraph and a numeral does not, and `MANUSCRIPT.md` keeps them for exactly
    that reason. The submitted document must not: JORS uses Vancouver numbered
    citations, and a draft carrying `[ravel2005]` in the prose plus a reference
    list annotated "(cited as [ravel2005])" reads as an unfinished submission —
    which is what the first outside reader called it.

    Numbering is not recomputed here. The reference list was already ordered by
    first appearance in the body, so reading the list back gives the same map
    the list itself prints, and the two cannot disagree.
    """
    numbers = {
        key: n
        for n, key in enumerate(
            re.findall(r"^\d+\. .*?_\(cited as `\[([^\]]+)\]`\)_", md, re.MULTILINE),
            start=1,
        )
    }
    if not numbers:
        return md
    md = re.sub(r"\s*_\(cited as `\[[^\]]+\]`\)_", "", md)

    def numeral(match: re.Match[str]) -> str:
        keys = [k.strip() for k in match.group(1).split(",") if k.strip()]
        if not all(k in numbers for k in keys):
            return match.group(0)
        return "(" + ", ".join(str(numbers[k]) for k in keys) + ")"

    return CITE_RE.sub(numeral, md)


FOOTNOTE_REF_RE = re.compile(r"\[\^([\w-]+)\]")
FOOTNOTE_DEF_RE = re.compile(r"^\[\^([\w-]+)\]:[ \t]*(.*?)(?=\n\n|\Z)", re.MULTILINE | re.DOTALL)


def footnotes_to_endnotes(md: str) -> str:
    """Turn markdown footnotes into a numbered Notes section before References.

    JORS places notes as endnotes ahead of the reference list. Pandoc has no
    docx endnote writer at all — it only emits real footnotes — so this is done
    in the source it reads rather than by post-processing the OOXML: each marker
    becomes a superscript numeral, each definition moves into a `## Notes` list,
    and the numbering follows first *use*, which is not the order the definitions
    happen to be written in.
    """
    definitions = {m.group(1): " ".join(m.group(2).split()) for m in FOOTNOTE_DEF_RE.finditer(md)}
    if not definitions:
        return md
    md = FOOTNOTE_DEF_RE.sub("", md)

    order: list[str] = []
    for match in FOOTNOTE_REF_RE.finditer(md):
        if match.group(1) in definitions and match.group(1) not in order:
            order.append(match.group(1))
    numbers = {key: n for n, key in enumerate(order, start=1)}
    md = FOOTNOTE_REF_RE.sub(
        lambda m: f"^{numbers[m.group(1)]}^" if m.group(1) in numbers else "",
        md,
    )

    notes = "## Notes\n\n" + "\n\n".join(f"{numbers[k]}. {definitions[k]}" for k in order) + "\n\n"
    return md.replace("## References\n", notes + "## References\n", 1)


def _alias_blocks() -> dict[str, str]:
    """Return the alias style definitions, keyed by the style id each declares."""
    blocks = re.findall(r"<w:style .*?</w:style>", PANDOC_STYLE_ALIASES, re.DOTALL)
    ids = [re.findall(r'w:styleId="([^"]+)"', b)[0] for b in blocks]
    return dict(zip(ids, blocks, strict=True))


def derive_reference_doc(template: Path, dest: Path) -> list[str]:
    """Copy `template`, adding the pandoc style ids it lacks. Returns those added."""
    with zipfile.ZipFile(template) as zin:
        styles = zin.read("word/styles.xml").decode("utf-8")
        present = set(re.findall(r'w:styleId="([^"]+)"', styles))
        missing = {k: v for k, v in _alias_blocks().items() if k not in present}
        patched = styles.replace("</w:styles>", "".join(missing.values()) + "</w:styles>")
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                body = (
                    patched.encode("utf-8")
                    if item.filename == "word/styles.xml"
                    else zin.read(item.filename)
                )
                zout.writestr(item, body)
    return list(missing)


def expected_image_count(state: dict[str, Any]) -> int:
    """How many image parts the document must embed, per the state file.

    Algorithms are rendered images too — typeset by LaTeX rather than plotted —
    but they are numbered in their own sequence, not the figures'. Both count.

    Listings do not, unless one still declares `rendered_as: "image"`. JORS asks
    authors to avoid images of text: a raster listing is not machine-readable,
    not searchable, and invisible to a screen reader. They are set as fenced code
    blocks instead, which pandoc styles with `SourceCode` and the syntax-token
    styles it has always written into the reference doc and never used. The
    committed `.tex`, `.pdf` and `.png` are deliberately left on disk — the
    typeset form is still the better artefact for a slide or a poster, and
    deleting a rendered figure to change how a document embeds it would throw
    away work that costs a TeX installation to reproduce.
    """
    floats = state.get("figures", []) + state.get("algorithms", [])
    listings = [x for x in state.get("listings", []) if x.get("rendered_as") == "image"]
    return len(floats) + len(listings)


def embedded_images(docx: Path) -> int:
    """Return how many image parts the document actually carries."""
    with zipfile.ZipFile(docx) as z:
        return sum(1 for n in z.namelist() if n.startswith("word/media/"))


def embedded_tables(docx: Path) -> int:
    """Return how many real Word tables the document carries."""
    with zipfile.ZipFile(docx) as z:
        return z.read("word/document.xml").decode("utf-8").count("<w:tbl>")


def markdown_tables(md: str) -> int:
    """Count pipe tables in the source: a header row followed by a delimiter row."""
    lines = md.splitlines()
    return sum(
        1
        for i, ln in enumerate(lines[:-1])
        if ln.lstrip().startswith("|") and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1])
    )


# Every part pandoc writes that can carry a style reference. `document.xml`
# alone is not enough: the footnote bodies live in their own part and referenced
# `FootnoteText` for months without the guard noticing.
STYLED_PARTS = (
    "word/document.xml",
    "word/footnotes.xml",
    "word/endnotes.xml",
    "word/header1.xml",
    "word/comments.xml",
)
STYLE_REF_RE = re.compile(r'w:(?:p|r|tbl)Style w:val="([^"]+)"')


def unresolved_styles(docx: Path) -> list[str]:
    """Return style ids the document references but does not define.

    This is the check that the silent Normal-fallback cannot evade: a heading
    that lost its style still *looks* like a paragraph, so only comparing the
    referenced ids against the defined ones catches it.

    It has to read every reference, not just paragraph ones in the body. The
    version that matched `w:pStyle` in `word/document.xml` alone shipped three
    undefined styles for as long as it existed — `VerbatimChar` above all, which
    is the *character* style pandoc puts on every inline code span, so every
    backticked identifier in the paper set as ordinary body text with nothing
    on the page to say so.
    """
    with zipfile.ZipFile(docx) as z:
        defined = set(re.findall(r'w:styleId="([^"]+)"', z.read("word/styles.xml").decode("utf-8")))
        names = set(z.namelist())
        used = {
            style
            for part in STYLED_PARTS
            if part in names
            for style in STYLE_REF_RE.findall(z.read(part).decode("utf-8"))
        }
    return sorted(used - defined)


def docx_has_comments(docx: Path) -> bool:
    """True when the document on disk carries Word review comments."""
    if not docx.exists():
        return False
    with zipfile.ZipFile(docx) as z:
        if "word/comments.xml" not in z.namelist():
            return False
        return b"<w:comment " in z.read("word/comments.xml")


def render_docx(markdown: str, state: dict[str, Any]) -> None:
    """Render the submission docx through pandoc against the venue template."""
    # The docx is a build output and this rewrites it in full, so review comments
    # written into it would be destroyed without trace. Refuse instead: they are
    # the author's own words and the render can always be repeated, which the
    # comments cannot.
    if docx_has_comments(DOCX):
        msg = (
            f"REFUSING to overwrite {DOCX.name}: it carries Word review comments that this "
            f"render would destroy.\n"
            f"  Read them out first:  uv run python manuscript/read_docx_comments.py "
            f"{DOCX} --toml\n"
            f"  Then move or delete the commented file and re-run."
        )
        raise SystemExit(msg)

    if shutil.which("pandoc") is None:
        msg = "pandoc not found on PATH — required for --docx"
        raise SystemExit(msg)
    if not JORS_TEMPLATE.exists():
        msg = f"missing venue template: {JORS_TEMPLATE}"
        raise SystemExit(msg)

    digest = hashlib.sha256(JORS_TEMPLATE.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        reference = tmpdir / "reference.docx"
        added = derive_reference_doc(JORS_TEMPLATE, reference)
        source = tmpdir / "submission.md"
        source_markdown = submission_markdown(markdown)
        source.write_text(source_markdown)
        # Pandoc stamps wall-clock time into docProps/core.xml, which made two
        # renders of identical input differ and the hash-based staleness gate
        # below report STALE for a document nobody had touched. It honours
        # SOURCE_DATE_EPOCH, so one variable fixes it. Same constant as
        # render_figures.py, which pinned it for the figures after exactly this.
        env = dict(os.environ)
        env.setdefault("SOURCE_DATE_EPOCH", "1700000000")  # 2023-11-14, fixed
        subprocess.run(
            [
                "pandoc",
                str(source),
                # -implicit_figures: the alt attribute must stay the screen-reader
                # description, not be promoted into a second visible caption.
                #
                # +subscript+superscript: chemistry and oxidation states are
                # typography, not mathematics. `Fe L~2,3~-edge` becomes a real
                # Word subscript *run* — inline, in-word, searchable, and read
                # aloud as text. Written as math instead it would need a base
                # inside the span; written as `$_{2,3}$`, with the base outside,
                # pandoc has to invent one (U+200B) and Word draws that empty
                # slot as a placeholder box floating away from the L. Genuine
                # mathematics still goes through tex_math_dollars to OMML, which
                # is Word's own equation format and toggles back to LaTeX in the
                # Equation ribbon. scripts/audit_latex.py enforces the split.
                "--from=gfm+tex_math_dollars+subscript+superscript-implicit_figures",
                "--to=docx",
                f"--reference-doc={reference}",
                # Figure paths are written relative to MANUSCRIPT.md so the
                # markdown renders on a git forge; pandoc reads the temp copy,
                # so it needs the real directory to resolve them against.
                f"--resource-path={DRAFT}",
                "-o",
                str(DOCX),
            ],
            check=True,
            env=env,
        )

    orphans = unresolved_styles(DOCX)
    if orphans:
        msg = f"BROKEN: {DOCX.name} references undefined styles: {', '.join(orphans)}"
        raise SystemExit(msg)

    wanted_tables = markdown_tables(source_markdown)
    got_tables = embedded_tables(DOCX)
    if got_tables != wanted_tables:
        msg = (
            f"BROKEN: {DOCX.name} has {got_tables} table(s), expected {wanted_tables} — "
            f"a pipe table whose cell contains an unescaped '|' (e.g. $|x|$ instead of "
            f"$\\lvert x \\rvert$) is silently parsed as prose, not as a table"
        )
        raise SystemExit(msg)

    embedded = embedded_images(DOCX)
    expected_images = expected_image_count(state)
    if embedded != expected_images:
        msg = (
            f"BROKEN: {DOCX.name} embeds {embedded} image(s), expected "
            f"{expected_images} — pandoc downgrades an unresolvable image to its "
            f"alt text and still exits 0"
        )
        raise SystemExit(msg)

    write_manifest(state, source_markdown, added)
    print(f"wrote {DOCX.relative_to(HERE.parent)}")
    print(f"  manifest: {MANIFEST.relative_to(HERE.parent)} (schema {MANIFEST_SCHEMA})")
    print(f"  template sha256: {digest}")
    print(f"  figures embedded: {embedded}")
    print(f"  tables rendered:  {got_tables}")
    print(f"  algorithms:       {len(state.get('algorithms', []))}")
    print(f"  listings:         {len(state.get('listings', []))}")
    print(f"  style aliases injected: {', '.join(added)}")
    print("  every referenced style resolves")


def _sha256(data: bytes | str) -> str:
    """Return the hex digest of `data`, encoding text as UTF-8 first."""
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def pandoc_version() -> str:
    """Return pandoc's first version line, for the render record."""
    out = subprocess.run(["pandoc", "--version"], check=True, capture_output=True, text=True)
    return out.stdout.splitlines()[0].strip()


def section_manifest(state: dict[str, Any]) -> list[dict[str, str]]:
    """List the rendered sections with the name the venue gives each one.

    The title is taken from the binding, not from the state file's own `title`
    field: the state carries no title at all for the end matter, and still calls
    availability/reuse by their pre-part-numbering names. The binding is what the
    render actually emits, so it is what the record should say.
    """
    by_role = {sec["role"]: sec for sec in state["sections"]}

    # Mirror the render order exactly, keywords included at its real position in
    # the front matter rather than appended wherever the binding happens to end.
    order: list[tuple[str, str | None]] = []
    for entry in JORS_BINDING:
        order.append(entry)
        if entry[0] == "abstract":
            order.extend(FRONT_MATTER_AFTER_ABSTRACT)

    out = []
    for role, heading in order:
        section = by_role.get(role)
        if section is None:
            continue
        part = JORS_PARTS.get(role)
        # `summary` is the title itself; availability and reuse are named by
        # their part header because they carry no heading of their own.
        title = "Title" if role == "summary" else (heading or part or role)
        record = {"role": role, "file": section["file"], "title": title}
        if part:
            record["part"] = part
        out.append(record)
    return out


def write_manifest(state: dict[str, Any], source_markdown: str, aliases: list[str]) -> None:
    """Record what the docx was built from, so staleness is detectable offline.

    The docx is the one artefact `--check` cannot re-derive without pandoc. Since
    pandoc's docx output turns out to be byte-reproducible here — the render
    strips the timestamp and commit lines before pandoc ever sees them — three
    hashes are enough to decide the question exactly: the source markdown, the
    venue template, and the docx itself.

    This replaces the schema-1 manifest written by the drafting tool that was
    never committed. That one recorded a 7-section shape and went stale the day
    the sections were rewritten, with nothing able to notice.
    """
    payload = {
        "schema": MANIFEST_SCHEMA,
        "venue": state["venue"]["id"],
        "docx": {
            "renderedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sha256": _sha256(DOCX.read_bytes()),
            "sourceSha256": _sha256(source_markdown),
            "templateSha256": _sha256(JORS_TEMPLATE.read_bytes()),
            "templatePath": str(JORS_TEMPLATE.relative_to(HERE.parent)),
            "pandoc": pandoc_version(),
            "figuresEmbedded": embedded_images(DOCX),
            "styleAliasesInjected": aliases,
        },
        "sections": section_manifest(state),
        "figures": [
            {
                "number": f["number"],
                "id": f["id"],
                "raster": f["files"]["raster_300dpi"],
                "sha256": _figure_sha256(f),
            }
            for f in sorted(state.get("figures", []), key=lambda x: x["number"])
        ],
        "tables": [{"number": t["number"], "id": t["id"]} for t in state.get("tables", [])],
        "references": {
            "total": len(state.get("references", [])),
            "registryResolved": sum(1 for r in state.get("references", []) if r.get("csl")),
        },
    }
    MANIFEST.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def docx_staleness(source_markdown: str) -> list[str]:
    """Return the reasons the docx on disk no longer matches its sources.

    Deliberately pandoc-free: it compares recorded hashes against current ones,
    so the check works identically on a machine that cannot render. Rendering
    still needs pandoc; noticing that a render is *due* does not.
    """
    if not MANIFEST.exists():
        return ["no render manifest — the docx has no recorded provenance"]
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("schema") != MANIFEST_SCHEMA:
        return [
            (
                f"render manifest is schema {manifest.get('schema')!r}, "
                f"expected {MANIFEST_SCHEMA} — re-render so figure hashes are recorded"
            ),
        ]
    if not DOCX.exists():
        return [f"{DOCX.name} does not exist"]

    record = manifest["docx"]
    reasons = []
    if record["sourceSha256"] != _sha256(source_markdown):
        reasons.append("the manuscript text changed since the docx was rendered")
    if record["templateSha256"] != _sha256(JORS_TEMPLATE.read_bytes()):
        reasons.append("the venue template changed since the docx was rendered")
    if record["sha256"] != _sha256(DOCX.read_bytes()):
        reasons.append(f"{DOCX.name} was modified after it was rendered")
    return reasons


def _figure_sha256(fig: dict[str, Any]) -> str | None:
    """Hash a registered figure's 300 dpi raster, or None when it is missing."""
    raster = HERE.parent / fig["files"]["raster_300dpi"]
    return _sha256(raster.read_bytes()) if raster.exists() else None


def figure_staleness(state: dict[str, Any]) -> list[str]:
    """Return the reasons a registered figure no longer matches the rendered draft.

    The failure this exists to catch: a figure is regenerated with new numbers
    while its caption and `quoted_numbers` in the state file keep the old ones.
    That is not hypothetical -- Figure 5 shipped a caption reading "for all ten
    implemented datasets" over an image whose own subtitle said "22 of 27", and
    nothing could notice, because the numbers a caption contradicts live inside a
    PNG that no source-level check can read.

    Hashes, not modification times: a file copied or checked out afresh has a new
    mtime and identical content, and that must not read as a stale figure. A
    regenerated figure whose pixels are unchanged is likewise not stale.
    """
    if not MANIFEST.exists():
        return ["no render manifest — the figures have no recorded provenance"]
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("schema") != MANIFEST_SCHEMA:
        return []  # docx_staleness already reports the schema; do not double-report

    recorded = {f["id"]: f for f in manifest.get("figures", [])}
    reasons = []
    for fig in sorted(state.get("figures", []), key=lambda x: x["number"]):
        fid, path = fig["id"], fig["files"]["raster_300dpi"]
        current = _figure_sha256(fig)
        if current is None:
            reasons.append(f"Figure {fig['number']} ({fid}): {path} does not exist")
            continue
        was = recorded.get(fid)
        if was is None:
            reasons.append(
                f"Figure {fig['number']} ({fid}) is registered but was not in the "
                "last render — its caption has never been checked against the image",
            )
        elif was.get("sha256") != current:
            reasons.append(
                f"Figure {fig['number']} ({fid}): the image changed since the draft "
                "was rendered — re-read its caption and quoted_numbers before "
                "re-rendering, they are not derived from the image",
            )
    reasons.extend(
        f"{fid} was rendered into the draft but is no longer registered"
        for fid in recorded.keys() - {f["id"] for f in state.get("figures", [])}
    )
    return reasons


def render_ris(state: dict[str, Any]) -> str:
    """Return an RIS library of the references, for import into EndNote/Zotero.

    Built from the structured `csl` block fetched once from Crossref/DataCite and
    stored in the state file, not re-fetched at render time — the render stays
    offline and deterministic. A reference without one (no DOI to resolve) is
    still emitted, from its Vancouver string, so the library is never silently
    short of an entry; `N1` flags it as needing manual completion.

    `ID` carries the citation key the prose uses (`[ravel2005]`), so a key in the
    text maps to a record in the library by inspection.
    """
    out: list[str] = []
    for ref in state.get("references", []):
        csl = ref.get("csl")
        if csl is None:
            out += [
                "TY  - GEN",
                f"ID  - {ref['key']}",
                f"TI  - {ref['vancouver']}",
                "N1  - No DOI: fields not resolved from a registry; complete by hand.",
            ]
        else:
            out.append(f"TY  - {csl['ris_type']}")
            out.append(f"ID  - {ref['key']}")
            out += [f"AU  - {a}" for a in csl.get("authors", [])]
            for tag, key in (
                ("TI", "title"),
                ("JO", "container"),
                ("PY", "year"),
                ("VL", "volume"),
                ("IS", "issue"),
                ("PB", "publisher"),
                ("UR", "url"),
            ):
                if csl.get(key):
                    out.append(f"{tag}  - {csl[key]}")
            pages = csl.get("pages")
            if pages:
                start, _, end = pages.partition("-")
                out.append(f"SP  - {start}")
                if end:
                    out.append(f"EP  - {end}")
            if ref.get("doi"):
                out.append(f"DO  - {ref['doi']}")
        out += ["ER  - ", ""]
    return "\n".join(out)


def main() -> None:
    """Render both artefacts, or verify they are up to date."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the rendered output differs from what is on disk",
    )
    ap.add_argument(
        "--docx",
        action="store_true",
        help="also render MANUSCRIPT.docx via pandoc against the JORS template",
    )
    args = ap.parse_args()

    state = json.loads(STATE.read_text())
    manuscript, unresolved = render_manuscript(state)
    todo = render_todo(state, unresolved)

    targets = {
        DRAFT / "MANUSCRIPT.md": manuscript,
        DRAFT / "TODO.md": todo,
        DRAFT / "references.ris": render_ris(state),
    }

    if args.check:
        stale = []
        for path, wanted in targets.items():
            current = path.read_text() if path.exists() else ""
            norm = lambda t: [ln for ln in t.splitlines() if not ln.startswith(PROVENANCE_STAMPS)]
            if norm(current) != norm(wanted):
                stale.append(path.name)
                sys.stdout.writelines(
                    difflib.unified_diff(
                        norm(current),
                        norm(wanted),
                        fromfile=f"{path.name} (on disk)",
                        tofile=f"{path.name} (rendered)",
                        lineterm="",
                        n=1,
                    ),
                )
                print()
        # The docx cannot be re-derived here without pandoc, so it is checked by
        # hash instead. That keeps `--check` runnable everywhere — a machine with
        # no pandoc can still notice that a render is due, which is the failure
        # this whole manifest exists to prevent.
        docx_reasons = docx_staleness(submission_markdown(manuscript))
        for reason in docx_reasons:
            print(f"{DOCX.name}: {reason}")

        # Figures are checked separately from the docx: a stale figure is a
        # content defect (a caption that no longer describes its image), not a
        # render that is merely due.
        figure_reasons = figure_staleness(state)
        for reason in figure_reasons:
            print(f"figure: {reason}")

        if stale or docx_reasons or figure_reasons:
            names = ", ".join(
                [
                    *stale,
                    *([DOCX.name] if docx_reasons else []),
                    *(["figures"] if figure_reasons else []),
                ],
            )
            flag = " --docx" if docx_reasons else ""
            print(f"STALE: {names} — run manuscript/render_manuscript.py{flag}")
            raise SystemExit(1)
        print("manuscript render is up to date (docx verified by hash)")
        return

    for path, content in targets.items():
        path.write_text(content)
        print(f"wrote {path.relative_to(HERE.parent)} ({len(content.splitlines())} lines)")
    if args.docx:
        render_docx(manuscript, state)
    if unresolved:
        print(f"note: {len(unresolved)} unresolved placeholder(s): {', '.join(unresolved)}")


if __name__ == "__main__":
    main()
