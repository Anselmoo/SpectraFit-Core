"""Anti-drift guard (COV-04): the docs Formula column must not silently diverge from
``oracles.models.MODEL_REGISTRY``.

Background: 34 model formulas were authored twice in independent LaTeX — once as
``PeakModel.formula_latex`` in ``python/oracles/models.py`` (numerically pinned
against the Rust kernel by ``tests/unit/oracles/test_wheel_eval.py``), and again by
hand in the Formula column of ``docs/reference/models/index.md``. A 2026-08-21 audit
found only 4 of 34 byte-identical, and two pairs (``log_normal``,
``split_pearson7``) had drifted into genuinely different mathematics before being
hand-corrected. Nothing pinned the two sources together — unlike the adjacent
wire-string parity that ``tests/parity/test_schema_parity.py`` genuinely enforces.

``docs/_render_model_formulas.py`` closes that gap going forward by rewriting the
content of ``<!-- formula:KEY -->...<!-- /formula -->`` marker comments from the
registry on every docs build. But the generator alone is not the guarantee: nothing
stops a hand-edit *inside* a marker after the generator last ran, or a new
``formula_latex`` shipping without ever getting a marker on the page at all. These
two tests are that guarantee:

* :func:`test_formula_markers_match_registry` — every marker already on the page
  must equal ``${MODEL_REGISTRY[key].formula_latex}$`` verbatim. A hand-edit inside
  a marker, or a registry change the generator was never re-run for, fails this.
* :func:`test_formula_marker_coverage` — every registry key with a non-empty
  ``formula_latex`` must eventually have a marker on the page. As of this test's
  introduction the page has zero markers (the migration patch that adds them is a
  separate, reviewed change — see the COV-04 report); this test **skips** rather
  than fails while that migration is incomplete, printing exactly which keys are
  still missing, and starts asserting full coverage for real the moment the last
  one gets a marker — no further change to this file required.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from oracles.models import MODEL_REGISTRY

_ROOT = Path(__file__).resolve().parents[2]
_PAGE = _ROOT / "docs" / "reference" / "models" / "index.md"

_MARKER_RE = re.compile(
    r"<!-- formula:(?P<key>[a-z0-9_]+) -->(?P<body>.*?)<!-- /formula -->",
    re.DOTALL,
)


def _page_text() -> str:
    assert _PAGE.exists(), f"model reference page missing: {_PAGE}"
    return _PAGE.read_text(encoding="utf-8")


def test_formula_markers_match_registry() -> None:
    """Every ``formula:KEY`` marker's body must equal the registry's LaTeX verbatim."""
    mismatches = []
    for match in _MARKER_RE.finditer(_page_text()):
        key, body = match.group("key"), match.group("body")
        model = MODEL_REGISTRY.get(key)
        if model is None:
            mismatches.append(f"{key}: marker present but no such MODEL_REGISTRY key")
            continue
        expected = f"${model.formula_latex}$"
        if body != expected:
            mismatches.append(f"{key}: marker has {body!r}, registry says {expected!r}")
    assert not mismatches, (
        "docs/reference/models/index.md formula marker(s) drifted from "
        "oracles.models.MODEL_REGISTRY (re-run `uv run --group docs python "
        "docs/_render_model_formulas.py`, or fix the hand-edit):\n" + "\n".join(mismatches)
    )


def test_formula_marker_coverage() -> None:
    """Every registry ``formula_latex`` must eventually get a ``formula:KEY`` marker.

    Skips while the COV-04 migration patch is still partial; asserts full coverage
    once every key has been migrated.
    """
    covered = {match.group("key") for match in _MARKER_RE.finditer(_page_text())}
    expected = {key for key, model in MODEL_REGISTRY.items() if model.formula_latex}
    missing = sorted(expected - covered)
    if missing:
        pytest.skip(
            f"{len(missing)}/{len(expected)} MODEL_REGISTRY formulas have no "
            f"<!-- formula:KEY --> marker yet in {_PAGE.relative_to(_ROOT)}: {missing} "
            "(expected until the COV-04 migration patch lands)",
        )
    assert covered >= expected
