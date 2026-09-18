"""Pin the release maturity metadata so an accidental revert to alpha is caught.

Design note (changed at the 0.1.0 release). This guard used to assert the exact
literal ``version == "0.1.0b1"``, deliberately, so that every beta bump required
a conscious edit here. That trade-off stopped paying at 0.1.0, for two reasons:

1. ``rrt`` now owns the version across ten targets (see
   ``[[tool.rrt.version_targets]]`` in ``pyproject.toml``). It does not rewrite
   tests, so an exact pin would leave a red suite after every single
   ``rrt bump`` — turning the guard into routine noise, which is how guards get
   deleted rather than heeded.
2. The literal pin never actually expressed the invariant. What matters is not
   "the version is exactly this string" but "the project has not silently
   regressed to alpha maturity". That is now asserted directly, and holds across
   bumps without edits.

So the exact-version assertion is gone and the anti-alpha invariant is asserted
on its own terms, in both places maturity is declared: the version string and
the trove classifiers.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

# PEP 440 alpha spellings: 0.1.0a1, 0.1.0alpha1, 0.1.0-a1, 0.1.0.a1 …
_ALPHA_MARKER = re.compile(r"[-_.]?(?:a|alpha)\d*$", re.IGNORECASE)


def _project() -> dict:
    return tomllib.loads(_PYPROJECT.read_text())["project"]


def test_version_is_not_an_alpha_prerelease() -> None:
    version = _project()["version"]
    assert not _ALPHA_MARKER.search(version), (
        f"version {version!r} carries an alpha pre-release marker; "
        "this project declares beta-or-later maturity"
    )


def test_version_is_semver_parseable() -> None:
    """``rrt bump`` parses the canonical version with a strict semver 2.0 regex.

    A PEP 440 pre-release spelling such as ``0.1.0b1`` is *not* valid semver, and
    while ``pyproject.toml`` carried one, every ``rrt bump`` — including
    ``--dry-run`` — aborted with ``Invalid semver``, so the repo could not cut a
    release at all. That was diagnosed and left open in ``DECISIONS.md``
    (2026-08-08 entry, "Trade-offs"); dropping to plain ``0.1.0`` resolved it.
    This test stops it silently regressing: a future pre-release must be spelled
    semver-style (``0.1.1-beta.1``), not PEP 440 style (``0.1.1b1``).
    """
    version = _project()["version"]
    semver = re.compile(
        r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
        r"(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?"
        r"(?:\+[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?$",
    )
    assert semver.match(version), (
        f"version {version!r} is not semver-parseable, so `rrt bump` cannot read "
        "it; spell pre-releases semver-style (0.1.1-beta.1), not PEP 440 style"
    )


def test_classifier_is_beta() -> None:
    classifiers = _project()["classifiers"]
    assert "Development Status :: 4 - Beta" in classifiers
    assert "Development Status :: 3 - Alpha" not in classifiers
