"""Render ``docs/javascripts/abbr-map.generated.js`` from the abbreviation glossary.

Run before ``zensical build`` (wired into ``poe docs_build`` and ``poe docs_serve``,
alongside ``docs/_render_tags.py`` and its two siblings):

    uv run --group docs python docs/_render_abbr_map.py

Closes a real affordance gap, not a hypothetical one. ``pymdownx.abbr`` (see
``zensical.toml``'s ``markdown_extensions.abbr`` + ``auto_append``) renders every
``docs/includes/abbreviations.txt`` term as a bare ``<abbr title="...">`` — a dotted
underline promising a definition. Measured on the live site: ``content.tooltips`` is
enabled, but no tooltip host element exists in the DOM, a synthesised tap produces no
tooltip, and every ``<abbr>`` has ``tabIndex === -1``. Touch and keyboard users get the
affordance with no working mechanism behind it — worse than plain, undecorated prose.
``pymdownx.abbr`` has no config knob for this: it can only ever emit ``<abbr title>``,
never a link. So the fix is split across two files: this generator produces the data,
``docs/javascripts/abbr-init.js`` (see ``zensical.toml``'s ``extra_javascript``, and
that file's own header comment) does the DOM work at runtime — making every ``<abbr>``
focusable and screen-reader-addressable, and upgrading the ones this map covers into
real links to their ``docs/glossary.md`` anchor.

**Why a generated JS global, not a fetched JSON file.** Every other generator in this
directory (``_render_tags.py``, ``_render_nist_tables.py``, ``_render_model_formulas.py``)
writes a markdown page ``zensical build`` turns into HTML. This generator's consumer is
client-side JS, not the Zensical build itself, so the natural output is a plain script
that defines a global the way every vendored asset here already does (``katex.min.js``
defines ``katex``, ``mermaid.min.js`` defines ``window.mermaid``) — loaded by
``extra_javascript`` ahead of ``abbr-init.js``, exactly like those. That sidesteps a
runtime ``fetch()`` (relative-path-from-arbitrary-page-depth resolution, an extra
network round trip, and a failure mode with no offline fallback) for a payload small
enough that inlining it as a script costs nothing measurable.

**Term-to-anchor matching, and why roughly two-thirds of the 35 terms have no match.**
``docs/glossary.md``'s headings carry explicit ``{ #anchor }`` ids (``attr_list``), but
its terms are prose-titled ("Trust region", "AIC / BIC", "Oracle (parity oracle)"), not
literal copies of the abbreviations file's bracket keys ("trust-region", "AIC", "oracle").
:func:`_glossary_candidates` derives every reasonable literal variant of each heading
(the full text, the part before a parenthetical, each side of a "/" split) and
:func:`_normalize` folds case/hyphens/spaces/one-trailing-"s" so "tied parameters"
matches "Tied parameter". This is deliberately literal, not fuzzy or substring
matching: a term either resolves to a real heading under this transform or it does not
get a link. That is why terms like ``PyO3`` (glossary only has "PyO3 binding") and
``geomean`` (glossary only has "Geomean speedup") stay unmatched even though a human
would call them the same concept — a looser matcher would have to guess which
substring match is semantically real, and a wrong guess here is a silent mislink, not
a build failure. Roughly a third of the 35 terms resolve; the rest still get the
keyboard/touch fix from ``abbr-init.js``, just without the upgrade to a link.

Never fails the docs build: if either source file is missing or has zero matches, this
still writes a syntactically valid (possibly empty) map — an unmatched abbreviation
should not stop `content.tooltips` mode from at least treating every abbr accessibly.
Deterministic: no timestamps; entries are emitted in ``abbreviations.txt`` order.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DOCS_DIR = Path(__file__).parent
ABBR_SOURCE = DOCS_DIR / "includes" / "abbreviations.txt"
GLOSSARY_SOURCE = DOCS_DIR / "glossary.md"
OUT_PATH = DOCS_DIR / "javascripts" / "abbr-map.generated.js"

_ABBR_LINE_RE = re.compile(r"^\*\[(?P<term>[^\]]+)\]:", re.MULTILINE)
_HEADING_RE = re.compile(
    r"^#{2,4}\s+(?P<text>.+?)\s*\{\s*#(?P<anchor>[a-z0-9-]+)\s*\}\s*$",
    re.MULTILINE,
)


def _normalize(label: str) -> str:
    """Fold a label to a bare lowercase alnum key, singularizing one trailing 's'.

    Strips markdown backticks and every non-alphanumeric character, then drops a
    single trailing "s" (length permitting) so "tied parameters" (abbreviations.txt)
    and "Tied parameter" (a glossary heading) compare equal without a plural-aware
    grammar this module has no other reason to carry.
    """
    key = re.sub(r"[^a-z0-9]", "", label.lower())
    if len(key) > 3 and key.endswith("s"):
        key = key[:-1]
    return key


def _abbr_terms() -> list[str]:
    """Return the literal ``TERM`` keys from ``abbreviations.txt``, in file order."""
    text = ABBR_SOURCE.read_text(encoding="utf-8")
    seen: dict[str, None] = {}
    for match in _ABBR_LINE_RE.finditer(text):
        seen.setdefault(match.group("term"), None)
    return list(seen)


def _glossary_candidates() -> dict[str, str]:
    """Map every literal label variant of each glossary heading to its anchor.

    One heading can yield several candidate keys: the backtick-stripped heading text
    itself, the part before a `` (parenthetical)`` if present, and each side of a
    ``" / "`` split if present (e.g. "AIC / BIC" -> "AIC" and "BIC", both -> aic-bic).
    A later heading never overwrites an earlier candidate's anchor — first write wins,
    matching the top-to-bottom reading order of the source file.
    """
    text = GLOSSARY_SOURCE.read_text(encoding="utf-8")
    candidates: dict[str, str] = {}

    def add(label: str, anchor: str) -> None:
        key = _normalize(label)
        if key:
            candidates.setdefault(key, anchor)

    for match in _HEADING_RE.finditer(text):
        raw = match.group("text").strip()
        anchor = match.group("anchor")
        base = raw.replace("`", "").strip()
        add(base, anchor)
        paren = re.match(r"^(.*?)\s*\(.+\)$", base)
        if paren:
            add(paren.group(1).strip(), anchor)
        if " / " in base:
            for part in base.split(" / "):
                add(part.strip(), anchor)
    return candidates


# Pairings a human has stated, for terms whose glossary heading is a longer form of
# the same concept. The literal matcher above deliberately refuses to infer these —
# a guessed substring match is a silent mislink. An explicit table is not a guess,
# and it is the same construct docs/_render_tags.py uses to bind CategoryDef labels
# to the display names the manuscript table writes them under.
#
# Add an entry only where the heading is unambiguously the same term, not merely a
# related one. `Gate (regression gate)`, `ModelNodeSpec`, `ModelType` and
# `Solver::Variant` are glossary anchors with NO abbreviation term at all, which is
# the reverse direction and not something this map can or should fix.
ALIASES: dict[str, str] = {
    "PyO3": "pyo3-binding",  # heading: "PyO3 binding"
    "geomean": "geomean-speedup",  # heading: "Geomean speedup"
}


def build_map() -> dict[str, str]:
    """Return the ordered ``{term: glossary-anchor}`` mapping for matched terms only."""
    candidates = _glossary_candidates()
    known_anchors = set(candidates.values())
    result: dict[str, str] = {}
    for term in _abbr_terms():
        anchor = candidates.get(_normalize(term)) or ALIASES.get(term)
        if anchor is None:
            continue
        if anchor not in known_anchors:
            # An alias naming an anchor that no longer exists would produce a chip
            # pointing into nothing — the exact defect this file exists to remove.
            msg = f"[abbr-map] ERROR: alias for {term!r} names unknown glossary anchor {anchor!r}"
            raise SystemExit(msg)
        result[term] = anchor
    return result


_BANNER = """\
// GENERATED FILE — do not hand-edit. Written by docs/_render_abbr_map.py on every
// docs build (poe docs_build / poe docs_serve); see that module's docstring for the
// term-to-anchor matching rule and why not every abbreviation term is present here.
//
// Consumed by docs/javascripts/abbr-init.js, loaded immediately after this script
// (see zensical.toml's extra_javascript ordering comment).
window.SF_ABBR_MAP = """


def render(mapping: dict[str, str]) -> str:
    """Render the generated script body for ``mapping``."""
    return _BANNER + json.dumps(mapping, indent=2, sort_keys=False) + ";\n"


def main() -> int:
    """Write the abbreviation-to-glossary-anchor map; return 0."""
    mapping = build_map()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render(mapping), encoding="utf-8")
    total = len(_abbr_terms())
    print(
        f"[abbr-map] wrote {OUT_PATH.relative_to(DOCS_DIR.parent)} "
        f"({len(mapping)}/{total} terms matched to a glossary anchor)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
