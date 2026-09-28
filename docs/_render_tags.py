"""Render ``docs/tags.md``, the tag index Zensical does not provide.

Zensical 0.0.52 populates page ``tags`` and ships ``partials/tags.html``, but
generates no tag *listing* — upstream states "Tag listings are currently not
supported". The shipped partial therefore takes its ``{% else %}`` branch and
emits ``<span class="md-tag">`` for every chip: 47 tagged pages, 12 distinct
tags, and not one of them clickable. Verified on the live site before this
existed.

That is not something ``zensical.toml`` can fix — there is no key for it. This
script supplies the missing half: a real index page, generated from the same
front-matter the chips are rendered from, so the two cannot disagree. The
companion ``overrides/partials/tags.html`` points each chip at the anchor this
page emits.

Written, like ``docs/performance/index.md`` and ``docs/reference/nist-strd.md``,
in full on every build and gitignored — a generated page cannot go stale in git,
only in a build.
"""

from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
OUT = DOCS / "tags.md"

FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)


def slug(tag: str) -> str:
    """Return the anchor slug for ``tag``.

    Mirrors the id ``overrides/partials/tags.html`` links to. Kept as a plain
    lowercase/hyphen transform rather than reusing the theme's heading slugifier
    so the two sides cannot drift apart on a punctuation edge case.
    """
    return "tag-" + re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")


def check_slug_contract(tags: list[str]) -> list[str]:
    """Return tags whose slug differs between this module and the Jinja partial.

    ``overrides/partials/tags.html`` builds the anchor with a filter chain that can
    only do ``lower`` + spaces-to-hyphens. :func:`slug` uses a regex over any
    non-alphanumeric run. They agree on every current tag; a tag containing other
    punctuation would make the chip point at an anchor this page never emits. That
    is exactly the class of silent dead link this whole change exists to remove, so
    it is a build failure rather than a warning.
    """
    return [t for t in tags if slug(t) != "tag-" + t.lower().replace(" ", "-")]


def collect() -> dict[str, list[tuple[str, str]]]:
    """Map each tag to the (title, url-path) pairs of the pages carrying it."""
    index: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for path in sorted(DOCS.rglob("*.md")):
        if path.name == "tags.md" or path.parent.name == "includes":
            continue
        text = path.read_text(encoding="utf-8")
        match = FRONT_MATTER.match(text)
        if match is None:
            continue
        block = match.group(1)
        tags_block = re.search(r"^tags:\n((?:\s*-\s*.+\n?)+)", block, re.MULTILINE)
        if tags_block is None:
            continue
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else path.stem
        title = re.sub(r"\s*\{.*\}\s*$", "", title)  # strip attr-list suffixes
        # Emit the SOURCE-relative .md path, not a built URL. Zensical resolves a
        # markdown link against the source file and then re-depths it for the
        # directory URL, so a hand-built `../reference/x/` from docs/tags.md came
        # out as `../../reference/x/` and 118 links failed the link audit. The
        # same convention every hand-written page here uses.
        url = str(path.relative_to(DOCS))
        for line in tags_block.group(1).splitlines():
            tag = line.strip().lstrip("-").strip()
            if tag:
                index[tag].append((title, url))
    return index


def render(index: dict[str, list[tuple[str, str]]]) -> str:
    """Render the index page, tags ordered by page count then name."""
    order = sorted(index, key=lambda t: (-len(index[t]), t.lower()))
    total = sum(len(v) for v in index.values())
    lines = [
        "---",
        "icon: lucide/tags",
        f"description: Every documentation page grouped by topic — {len(order)} tags across {total} page assignments.",
        "---",
        "",
        "# Tags",
        "",
        (
            f"{len(order)} tags across {total} page assignments. "
            "Tag chips at the top of a page link here."
        ),
        "",
    ]
    for tag in order:
        pages = sorted(index[tag], key=lambda p: p[0].lower())
        lines += [f"## {tag} {{ #{slug(tag)} }}", "", f"{len(pages)} pages.", ""]
        lines += [f"- [{title}]({url})" for title, url in pages]
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    """Write the tag index; return 0."""
    index = collect()
    divergent = check_slug_contract(list(index))
    if divergent:
        print(
            f"[tags] ERROR: {divergent} slug differently in _render_tags.py and "
            "overrides/partials/tags.html — their chips would link to a dead anchor.",
            file=sys.stderr,
        )
        return 1
    if not index:
        print("[tags] no tagged pages found; writing a placeholder", file=sys.stderr)
    OUT.write_text(render(index), encoding="utf-8")
    print(f"[tags] wrote {OUT.relative_to(DOCS.parent)} ({len(index)} tags)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
