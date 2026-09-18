#!/usr/bin/env python3
"""Extract Word review comments from a .docx, with the text each one anchors to.

WHY THIS EXISTS. Reviewing in Word is the natural way to mark up a manuscript,
but `MANUSCRIPT.docx` is a build output: `render_manuscript.py --docx` rewrites
it in full on every run, so comments written into it are one render away from
being lost. This reads them out into something durable — the author-check
questions file — before that happens, and `render_docx` refuses to overwrite a
commented file so the loss cannot happen silently.

Word stores a comment's TEXT in `word/comments.xml` and its ANCHOR as
`w:commentRangeStart`/`w:commentRangeEnd` markers surrounding runs in
`word/document.xml`. Neither half is useful alone: the text without the anchor is
an untethered remark, and this pairs them, which is the same rule the review
panel applies to its own findings.

    python3 manuscript/read_docx_comments.py MANUSCRIPT.docx            # human-readable
    python3 manuscript/read_docx_comments.py MANUSCRIPT.docx --toml     # QUESTIONS.toml blocks
    python3 manuscript/read_docx_comments.py MANUSCRIPT.docx --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def has_comments(docx: Path) -> bool:
    """True when the document carries at least one review comment."""
    if not docx.exists():
        return False
    with zipfile.ZipFile(docx) as z:
        if "word/comments.xml" not in z.namelist():
            return False
        return b"<w:comment " in z.read("word/comments.xml")


def read_comments(docx: Path) -> list[dict[str, str]]:
    """Return each comment with its author, text, and the passage it anchors to."""
    with zipfile.ZipFile(docx) as z:
        if "word/comments.xml" not in z.namelist():
            return []
        comments_xml = z.read("word/comments.xml").decode("utf-8")
        document_xml = z.read("word/document.xml").decode("utf-8")

    out: list[dict[str, str]] = []
    for block in re.findall(r"<w:comment\b.*?</w:comment>", comments_xml, re.DOTALL):
        cid = (re.search(r'w:id="(\d+)"', block) or [None, ""])[1]
        author = (re.search(r'w:author="([^"]*)"', block) or [None, ""])[1]
        date = (re.search(r'w:date="([^"]*)"', block) or [None, ""])[1]
        text = " ".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", block, re.DOTALL)).strip()
        out.append(
            {
                "id": cid,
                "author": author,
                "date": date,
                "comment": text,
                "anchor": _anchor_text(document_xml, cid),
            },
        )
    return out


def _anchor_text(document_xml: str, cid: str) -> str:
    """Return the document text between this comment's range markers."""
    start = re.search(rf'<w:commentRangeStart[^>]*w:id="{cid}"[^>]*/>', document_xml)
    end = re.search(rf'<w:commentRangeEnd[^>]*w:id="{cid}"[^>]*/>', document_xml)
    if not (start and end) or end.start() <= start.end():
        return ""
    span = document_xml[start.end() : end.start()]
    return " ".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", span, re.DOTALL)).strip()


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def to_toml(comments: list[dict[str, str]]) -> str:
    """Render the comments as QUESTIONS.toml blocks, kind left for the author."""
    parts = [
        "# Extracted from Word comments. `kind` is deliberately left as TODO on every",
        "# block: it selects the probe, so guessing it would run the wrong one and",
        "# report the result as an answer. Set each one before indexing.",
        "",
    ]
    for c in comments:
        anchor = c["anchor"] or "(no anchored text — comment was not attached to a range)"
        parts += [
            "[[question]]",
            'kind = "TODO"  # claim | evidence | gap | correctness | framing | practice',
            'target = "manuscript/draft/MANUSCRIPT.docx"',
            f'asked = """{_esc(c["comment"])}"""',
            f'matters = "Word comment {c["id"]} by {c["author"]}, {c["date"][:10]}"',
            f'satisfied_by = "resolves the passage: {_esc(anchor[:160])}"',
            "",
        ]
    return "\n".join(parts)


def main() -> None:
    """Read comments out of a .docx and print them in the requested form."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("docx", type=Path)
    ap.add_argument("--toml", action="store_true", help="emit QUESTIONS.toml blocks")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    if not args.docx.exists():
        sys.exit(f"no such file: {args.docx}")
    comments = read_comments(args.docx)
    if not comments:
        print(f"{args.docx.name}: no review comments found.")
        return
    if args.json:
        print(json.dumps(comments, indent=2, ensure_ascii=False))
    elif args.toml:
        print(to_toml(comments))
    else:
        print(f"{args.docx.name}: {len(comments)} comment(s)\n")
        for c in comments:
            print(f"  [{c['id']}] {c['author']} {c['date'][:10]}")
            print(f"      on: {c['anchor'][:100] or '(unanchored)'}")
            print(f"      >>  {c['comment']}\n")


if __name__ == "__main__":
    main()
