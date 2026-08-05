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

#: Site-root-relative prefixes that exist in the DEPLOYED tree but never in a
#: local `site/` build, because `pages` assembles them from other jobs'
#: artifacts (.gitlab/60-pages.yml: docs -> public/, rustdoc ->
#: public/rust-api/, web bundle -> public/web/, coverage atlas ->
#: public/reports/, benchmark bundle -> public/report.html). Linking to them
#: is correct; resolving them here is impossible. Kept as an explicit,
#: commented list rather than a broad "ignore anything under these names"
#: rule, so a genuine typo in a docs link still fails. Any addition here
#: should correspond to a real `cp` in 60-pages.yml.
#:
#: 2026-08-04: these are matched against the target's resolved path relative
#: to SITE (see `_is_ci_assembled`), NOT the raw href string. Docs links to
#: these now use page-relative hrefs (`../report.html` etc.) rather than
#: root-absolute (`/report.html`) ones — GitLab Pages serves this project
#: from its own unique domain root, but GitHub Pages serves it as a project
#: page under /SpectraFit-Core/, so a root-absolute link 404s there. Matching
#: on the raw string would have silently stopped exempting these the moment
#: the docs source switched to relative links.
_CI_ASSEMBLED = ("rust-api/", "reports/", "web/", "report.html")


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
    """Return the internal references in *html* (CI-assembled ones included —
    filtering those requires resolving against the page, done by the caller).
    """
    parser = _HrefCollector()
    parser.feed(html)
    out = []
    for ref in parser.refs:
        ref = ref.strip()
        if not ref or ref.startswith("#") or _EXTERNAL.match(ref):
            continue
        path = urlsplit(ref).path  # drop ?query and #fragment
        if not path:
            continue
        out.append(unquote(path))
    return out


def _resolve_candidate(page: Path, target: str) -> Path | None:
    """Resolve *target*, as written on *page*, to an absolute path under SITE.

    Returns ``None`` for a traversal escaping the site root (a failure, not
    an exception).
    """
    base = SITE if target.startswith("/") else page.parent
    candidate = (base / target.lstrip("/")).resolve()
    try:
        candidate.relative_to(SITE.resolve())
    except ValueError:
        return None
    return candidate


def _is_ci_assembled(page: Path, target: str) -> bool:
    """True if *target* resolves under one of the `_CI_ASSEMBLED` prefixes.

    Resolves relative targets against *page* first (see `_CI_ASSEMBLED`'s own
    docstring for why matching the raw href string isn't enough once docs
    links to these are page-relative rather than root-absolute).
    """
    candidate = _resolve_candidate(page, target)
    if candidate is None:
        return False
    # `Path.as_posix()` never has a trailing slash, so a target that resolves
    # to exactly a directory prefix itself (e.g. ".../web/" -> site/web, no
    # nested path) would otherwise miss a directory-style `_CI_ASSEMBLED`
    # entry like "web/" — "web".startswith("web/") is False. Checking both
    # the bare and slash-suffixed form handles the directory-itself case
    # without falsely matching an unrelated sibling like "web-extra".
    site_relative = candidate.relative_to(SITE.resolve()).as_posix()
    return site_relative.startswith(_CI_ASSEMBLED) or (site_relative + "/").startswith(
        _CI_ASSEMBLED
    )


def _resolves(page: Path, target: str) -> bool:
    """True if *target*, as written on *page*, points at something in the site."""
    candidate = _resolve_candidate(page, target)
    if candidate is None:
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
            if _is_ci_assembled(page, target):
                continue
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
