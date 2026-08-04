"""Every internal link in the built docs site resolves to something on disk.

This exists because 17 of 17 section-index cards shipped as dead links. They
passed source review, they passed ``zensical build --strict``, and they passed
the entire test suite. ``--strict`` validates nav entries and snippet includes;
it does not resolve hrefs that a Jinja template generates.

The specific failure was a collision of two conventions in one expression:
``overrides/section-index.html`` renders ``{{ card.link | url }}``, ``| url``
resolves its argument against the site root and then prefixes the page's own
depth, and the front-matter held page-relative ``.md`` source paths. Zensical
also publishes directory urls, so no ``.md`` file exists in the built tree at
any depth. Every card 404'd.

Neither half is visible in a diff. Only resolving built hrefs against the built
tree catches it, which is what this does.

Requires a built site: run ``uv run poe docs_build`` first. Skips (loudly)
rather than failing when ``site/`` is absent, so a checkout without a build
does not report a false failure — the docs CI jobs build before anything else
runs, and a local run without a build has nothing to check.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE = REPO_ROOT / "site"

#: Schemes that leave the site; not our problem to resolve.
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)

#: Root-relative paths that exist in the DEPLOYED tree but never in a local
#: `site/` build, because `pages` assembles them from other jobs' artifacts
#: (.gitlab/60-pages.yml: docs -> public/, rustdoc -> public/rust-api/, web
#: bundle -> public/web/, coverage atlas -> public/reports/, benchmark bundle
#: -> public/report.html). Linking to them is correct; resolving them here is
#: impossible. Kept as an explicit, commented list rather than a broad "ignore
#: root-relative" rule, so a genuine typo in a root-relative docs link still
#: fails. Any addition here should correspond to a real `cp` in 60-pages.yml.
_CI_ASSEMBLED = ("/rust-api/", "/reports/", "/web/", "/report.html")


class _HrefCollector(HTMLParser):
    """Collect href/src values. Deliberately not a regex over raw HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.refs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        wanted = (
            "href"
            if tag in {"a", "link"}
            else "src"
            if tag in {"img", "script"}
            else None
        )
        if wanted is None:
            return
        for name, value in attrs:
            if name == wanted and value:
                self.refs.append(value)


def _internal_targets(html: str) -> list[str]:
    """Return the internal, resolvable references in *html*."""
    parser = _HrefCollector()
    parser.feed(html)
    out = []
    for ref in parser.refs:
        ref = ref.strip()
        if not ref or ref.startswith("#") or _EXTERNAL.match(ref):
            continue
        path = urlsplit(ref).path  # drop ?query and #fragment
        if not path or path.startswith(_CI_ASSEMBLED):
            continue
        out.append(unquote(path))
    return out


def _resolves(page: Path, target: str) -> bool:
    """True if *target*, as written on *page*, points at something in the site."""
    base = SITE if target.startswith("/") else page.parent
    candidate = (base / target.lstrip("/")).resolve()
    try:  # a traversal escaping the site root is a failure, not an exception
        candidate.relative_to(SITE.resolve())
    except ValueError:
        return False
    return candidate.is_file() or (candidate / "index.html").is_file()


@pytest.fixture(scope="module")
def pages() -> list[Path]:
    if not SITE.is_dir():
        pytest.skip(f"{SITE} not built — run `uv run poe docs_build` first")
    found = sorted(SITE.rglob("*.html"))
    if not found:
        pytest.skip(f"{SITE} exists but contains no HTML — stale or partial build")
    return found


def test_site_has_pages(pages: list[Path]) -> None:
    """Guard the guard: an empty crawl would make every other check vacuous."""
    assert len(pages) > 10, f"only {len(pages)} pages found under {SITE}"


def test_no_internal_link_is_broken(pages: list[Path]) -> None:
    """No internal href/src in the built site 404s."""
    broken: list[str] = []
    checked = 0
    for page in pages:
        html = page.read_text(encoding="utf-8", errors="replace")
        for target in _internal_targets(html):
            checked += 1
            if not _resolves(page, target):
                broken.append(f"{page.relative_to(SITE)} -> {target}")

    assert checked > 50, (
        f"only {checked} internal references found across {len(pages)} pages; "
        "the collector is probably not matching, which would make this test vacuous"
    )
    assert not broken, (
        f"{len(broken)} broken internal link(s) of {checked} checked:\n  "
        + "\n  ".join(sorted(broken)[:25])
        + ("\n  …" if len(broken) > 25 else "")
    )


def test_section_cards_resolve(pages: list[Path]) -> None:
    """The specific regression: every `.sf-card` href resolves.

    Called out separately from the sweep above so the failure message names the
    thing that actually broke, rather than burying 17 cards in a general list.
    """
    card_href = re.compile(r'class="sf-card"\s+href="([^"]+)"')
    broken, total = [], 0
    for page in pages:
        html = page.read_text(encoding="utf-8", errors="replace")
        for target in card_href.findall(html):
            total += 1
            if not _resolves(page, urlsplit(target).path):
                broken.append(f"{page.relative_to(SITE)} -> {target}")

    assert total > 0, "no .sf-card links found — has the template or class changed?"
    assert not broken, (
        f"{len(broken)} of {total} section cards are dead:\n  " + "\n  ".join(broken)
    )
