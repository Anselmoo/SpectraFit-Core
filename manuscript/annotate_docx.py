#!/usr/bin/env python3
"""Attach review comments to a .docx as real Word margin comments.

The mirror of `read_docx_comments.py`: that one reads an author's comments out
of a reviewed document, this one writes a reviewer's comments in. Together they
close the loop, a review can be delivered in the tool the author actually reads
the manuscript in rather than as a separate markdown file they have to hold
beside it.

Anchoring is by literal text match. Each annotation names a short span that must
appear in the document exactly once; the comment is attached to the run
containing it. A span that is missing, or that occurs more than once, is
reported and skipped rather than guessed at, because a review comment pinned to
the wrong sentence is worse than one that did not land.

**This never writes to its input.** The output is a separate file, and the
default refuses to overwrite an existing one. That matters here: the repository's
renderer refuses to overwrite a .docx carrying comments, so writing annotations
into `manuscript/draft/MANUSCRIPT.docx` would block every later render until
someone worked out why.

Usage::

    python3 manuscript/annotate_docx.py IN.docx annotations.json OUT.docx

`annotations.json` is a list of objects::

    [{"author": "The Prospective User",
      "anchor": "median solve time is 15.8 times shorter",
      "text": "This is the paper's promise to me and it is the wrong one."}]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _initials(author: str) -> str:
    """Word shows these in the comment bubble; keep them short and stable."""
    parts = [p for p in re.split(r"[\s-]+", author) if p and p[0].isupper()]
    return "".join(p[0] for p in parts)[:4] or "R"


def _comment_xml(cid: int, author: str, text: str, when: str) -> str:
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>'
        for line in (text.split("\n") or [""])
    )
    return (
        f'<w:comment w:id="{cid}" w:author="{escape(author)}" '
        f'w:date="{when}" w:initials="{escape(_initials(author))}">{body}</w:comment>'
    )


def _splice_comments(comments_xml: str, new_comments: list[str]) -> str:
    """Append comment elements to the comments part, however it is shaped.

    An empty comments part is written self-closing (`<w:comments ... />`) by
    pandoc, so there is no `</w:comments>` to append before. Appending to the
    closing tag alone silently does nothing on exactly the documents this tool
    is most often pointed at: freshly rendered ones with no comments yet.
    """
    if not new_comments:
        return comments_xml
    body = "".join(new_comments)
    if "</w:comments>" in comments_xml:
        return comments_xml.replace("</w:comments>", body + "</w:comments>")
    # Self-closing root: reopen it, then close it after the new children.
    opened = re.sub(r"(<w:comments\b[^>]*?)\s*/>", r"\1>", comments_xml, count=1)
    if opened == comments_xml:
        msg = "comments.xml has neither a closing tag nor a self-closing root"
        raise SystemExit(msg)
    return opened + body + "</w:comments>"


def _anchor_run(doc: str, anchor: str) -> tuple[int, int] | None:
    """Locate the <w:r> element whose text contains `anchor`, exactly once.

    Word splits a paragraph into runs at every formatting change, so an anchor
    spanning a bold word or a citation will not sit inside one run. Anchors are
    therefore chosen from plain prose; one that does not resolve is reported.
    """
    hits = []
    for m in re.finditer(r"<w:r(?:\s[^>]*)?>.*?</w:r>", doc, re.DOTALL):
        run = m.group(0)
        plain = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", run, re.DOTALL))
        if anchor in plain:
            hits.append((m.start(), m.end()))
    return hits[0] if len(hits) == 1 else None


def annotate(src: Path, annotations: list[dict], dst: Path, *, force: bool) -> int:
    """Write `src` plus the annotations to `dst`, never touching `src` itself."""
    if dst.exists() and not force:
        print(f"error: {dst} exists; pass --force to replace it", file=sys.stderr)
        return 1
    shutil.copy2(src, dst)

    with zipfile.ZipFile(dst) as z:
        parts = {n: z.read(n) for n in z.namelist()}

    doc = parts["word/document.xml"].decode("utf8")
    comments = parts["word/comments.xml"].decode("utf8")
    when = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Highest existing id, so we append rather than collide.
    existing = [int(m) for m in re.findall(r'<w:comment w:id="(\d+)"', comments)]
    next_id = max(existing, default=-1) + 1

    made, skipped = [], []
    # Apply from the end of the document backwards, so each splice leaves the
    # offsets of the not-yet-applied anchors untouched.
    located = []
    for ann in annotations:
        span = _anchor_run(doc, ann["anchor"])
        if span is None:
            skipped.append(ann)
        else:
            located.append((span, ann))
    located.sort(key=lambda item: item[0][0], reverse=True)

    new_comments = []
    for (start, end), ann in located:
        cid = next_id
        next_id += 1
        run = doc[start:end]
        doc = (
            doc[:start]
            + f'<w:commentRangeStart w:id="{cid}"/>'
            + run
            + f'<w:commentRangeEnd w:id="{cid}"/>'
            + '<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>'
            + f'<w:commentReference w:id="{cid}"/></w:r>'
            + doc[end:]
        )
        new_comments.append(_comment_xml(cid, ann["author"], ann["text"], when))
        made.append(ann)

    comments = _splice_comments(comments, new_comments)
    parts["word/document.xml"] = doc.encode("utf8")
    parts["word/comments.xml"] = comments.encode("utf8")

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)

    # Read the result back and count what is actually in it. Reporting the
    # number we meant to write is how a silent no-op gets announced as a
    # success: pandoc emits an EMPTY comments part as a self-closing
    # `<w:comments .../>`, so an append that looks for a closing tag finds
    # nothing, changes nothing, and returns cleanly.
    with zipfile.ZipFile(dst) as z:
        written = z.read("word/comments.xml").decode("utf8")
    landed = len(re.findall(r"<w:comment\s", written))
    if landed != len(made):
        print(
            f"error: meant to attach {len(made)} comment(s) but {landed} are in "
            f"{dst.name}; the file has been left in place for inspection.",
            file=sys.stderr,
        )
        return 1

    print(f"wrote {dst}")
    print(f"  {landed} comment(s) attached (verified by re-reading the file)")
    if skipped:
        print(f"  {len(skipped)} anchor(s) did NOT resolve uniquely and were skipped:")
        for ann in skipped:
            print(f"    [{ann['author']}] {ann['anchor'][:60]!r}")
    return 0


def main() -> int:
    """Attach the annotations to a copy of the document."""
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("source", type=Path)
    ap.add_argument("annotations", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    data = json.loads(args.annotations.read_text())
    return annotate(args.source, data, args.output, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
