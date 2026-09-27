"""Every docs generator `poe docs_build` runs must also run in CI.

`poe docs_build` is the reference sequence: it renders each generated page,
then calls `zensical build`. Both CI docs jobs re-implement that sequence by
hand rather than invoking the task, because each interleaves provider-specific
steps (artifact fetches, `PYTHONPATH`, cache dirs) between the renderers.

That duplication drifts. It did: `docs/_render_nist_tables.py` and
`docs/_render_model_formulas.py` were added to `docs_build` and never copied
into either CI job, so `docs/reference/nist-strd.md` -- which is generated,
untracked, and listed in `zensical.toml`'s `nav` -- did not exist when
`zensical build` ran there.

The failure that produced is worth stating, because it is not the obvious one.
A nav entry whose file is missing cannot be resolved to a built URL, so the raw
`.md` path is emitted into the nav of *every* page. The link checker then
reports a broken internal link on all of them -- 66 in GitLab pipeline 368757 --
on pages that never mention NIST. The local `poe docs_build` cannot catch it:
it renders the file, and it does not run the link checker.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Each CI surface that runs `zensical build` and therefore needs every page
# the nav references to exist on disk first.
CI_DOCS_SURFACES = (
    Path(".gitlab/65-docs.yml"),
    Path(".github/workflows/docs-pages.yml"),
)

GENERATOR_RE = re.compile(r"\bdocs/[A-Za-z0-9_/]+\.py\b")
BUILD_RE = re.compile(r"zensical build")


def _docs_build_generators() -> list[str]:
    """Return the `docs/*.py` generators `poe docs_build` runs, in order."""
    with (ROOT / "pyproject.toml").open("rb") as fh:
        shell = tomllib.load(fh)["tool"]["poe"]["tasks"]["docs_build"]["shell"]
    seen: dict[str, None] = {}
    for match in GENERATOR_RE.findall(shell):
        seen.setdefault(match, None)
    return list(seen)


def test_docs_build_declares_generators() -> None:
    """Guard the guard: a docs_build that parses to nothing proves nothing."""
    generators = _docs_build_generators()
    assert generators, "no docs/*.py generators found in poe docs_build"


@pytest.mark.parametrize("surface", CI_DOCS_SURFACES, ids=lambda p: p.name)
def test_ci_runs_every_docs_build_generator(surface: Path) -> None:
    """Each CI docs job must invoke every generator `poe docs_build` invokes."""
    path = ROOT / surface
    assert path.exists(), f"{surface} is missing; update CI_DOCS_SURFACES"
    text = path.read_text()

    missing = [g for g in _docs_build_generators() if g not in text]
    assert not missing, (
        f"{surface} does not run: {', '.join(missing)}.\n"
        "These render pages that zensical.toml's nav references. A nav entry "
        "whose file is absent emits a raw .md path into every page's nav, so "
        "the link gate fails site-wide. Add them before `zensical build`, or "
        "drop them from docs_build if they are genuinely no longer needed."
    )


@pytest.mark.parametrize("surface", CI_DOCS_SURFACES, ids=lambda p: p.name)
def test_ci_runs_generators_before_zensical_build(surface: Path) -> None:
    """Each generator must run *before* `zensical build`, not merely appear.

    `test_ci_runs_every_docs_build_generator` only checks membership (`g in
    text`) -- it is blind to position. A generator pasted BELOW the build
    step would still satisfy that test while reproducing exactly the
    site-wide nav corruption described in this module's docstring (a nav
    entry whose file is not yet on disk when `zensical build` runs -- 66
    broken links, pipeline 368757). This test checks order instead.
    """
    path = ROOT / surface
    text = path.read_text()

    build_matches = list(BUILD_RE.finditer(text))
    assert build_matches, f"{surface} has no `zensical build` invocation"
    # The last match is the real invocation: both CI files also mention
    # "zensical build" in prose comments earlier (e.g. "a full `zensical
    # build`" describing the job), which would otherwise be mistaken for the
    # build step itself and make every generator look "out of order".
    build_pos = build_matches[-1].start()

    generators = _docs_build_generators()
    out_of_order = []
    for generator in generators:
        positions = [m.start() for m in re.finditer(re.escape(generator), text)]
        if not positions:
            # Missing entirely is test_ci_runs_every_docs_build_generator's job.
            continue
        if min(positions) > build_pos:
            out_of_order.append(generator)

    assert not out_of_order, (
        f"{surface} runs `zensical build` before: {', '.join(out_of_order)}.\n"
        "A generator invoked after `zensical build` renders its page too "
        "late for the nav to resolve it, corrupting every page's nav link "
        "(see this module's docstring). Move it above the `zensical build` "
        "step."
    )
