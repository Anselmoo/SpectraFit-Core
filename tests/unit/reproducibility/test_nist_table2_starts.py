"""Unit tests of the NIST table's start selection and its "least accurate" reductions.

No solver runs here: the selection, the per-start summary and the scipy standard-error
reduction are pure functions tested on synthetic values.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from oracles.audit.nist import _RECIPES

FIGURES = Path(__file__).resolve().parents[3] / "reproducibility" / "figures"


@pytest.fixture(scope="module")
def nt() -> ModuleType:
    """``nist_table2.py`` imported by path (its sibling ``nist_head_to_head`` on the path)."""
    sys.path.insert(0, str(FIGURES))
    try:
        spec = importlib.util.spec_from_file_location(
            "_repro_nist_table2",
            FIGURES / "nist_table2.py",
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # pydantic resolves annotations via the module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(FIGURES))
    return module


# ---------------------------------------------------------------- least accurate


def test_least_accurate_picks_the_minimum(nt: ModuleType) -> None:
    assert nt.least_accurate({"b1": 9.1, "b2": 6.4, "b3": 7.0}) == ("b2", 6.4)


def test_least_accurate_tie_goes_to_the_first_parameter_in_nist_order(nt: ModuleType) -> None:
    assert nt.least_accurate({"b1": 8.0, "b2": 5.5, "b3": 5.5}) == ("b2", 5.5)


def test_least_accurate_ignores_missing_values(nt: ModuleType) -> None:
    assert nt.least_accurate({"b1": None, "b2": 7.25, "b3": None}) == ("b2", 7.25)


def test_least_accurate_of_nothing_is_none(nt: ModuleType) -> None:
    assert nt.least_accurate({"b1": None}) is None
    assert nt.least_accurate({}) is None


def test_least_accurate_keeps_a_zero_and_the_cap(nt: ModuleType) -> None:
    assert nt.least_accurate({"b1": 15.0, "b2": 0.0}) == ("b2", 0.0)
    assert nt.least_accurate({"b1": 15.0, "b2": 15.0}) == ("b1", 15.0)


# ---------------------------------------------------------------- starts


@pytest.mark.parametrize("recipe", _RECIPES, ids=[r.name for r in _RECIPES])
def test_start_values(nt: ModuleType, recipe) -> None:
    from importlib import import_module

    module = import_module(f"oracles.nist_strd.{recipe.name.lower()}")
    assert nt.start_values(recipe, "START2") is recipe.start
    assert nt.start_values(recipe, "START1") == module.START1
    assert set(nt.start_values(recipe, "START1")) == set(recipe.certified)


def test_unknown_start_is_rejected(nt: ModuleType) -> None:
    with pytest.raises(ValueError, match="start"):
        nt.start_values(_RECIPES[0], "START3")


@pytest.mark.parametrize(
    ("argv", "start"),
    [([], "START2"), (["--start", "START1"], "START1"), (["--start", "both"], "both")],
)
def test_cli_start_option(nt: ModuleType, argv: list[str], start: str) -> None:
    assert nt.parse_args(argv).start == start


def test_cli_rejects_other_starts(nt: ModuleType) -> None:
    with pytest.raises(SystemExit):
        nt.parse_args(["--start", "START3"])


@pytest.mark.parametrize(
    ("start", "tol", "name"),
    [
        ("START2", 1e-12, "nist_table2.json"),
        ("START2", 1e-15, "nist_table2_tol1e15.json"),
        ("START1", 1e-12, "nist_table2_start1.json"),
        ("START1", 1e-15, "nist_table2_start1_tol1e15.json"),
        ("both", 1e-12, "nist_table2_both.json"),
    ],
)
def test_default_output_names(nt: ModuleType, start: str, tol: float, name: str) -> None:
    assert nt.default_out(start, tol).name == name


# ---------------------------------------------------------------- per-start summary


def _cell(nt: ModuleType, dataset: str, impl: str, lre: float | None, success: bool | None, **kw):
    return nt.NistCell(
        dataset=dataset,
        difficulty="Lower",
        start="START1",
        implementation=impl,
        success=success,
        termination=kw.get("termination", "converged"),
        error=kw.get("error"),
        param_lre={} if lre is None else {"b1": lre},
        param_lre_min=lre,
        param_lre_min_name=None if lre is None else "b1",
        stderr_lre={},
        stderr_lre_min=None,
        stderr_lre_min_name=None,
        stderr_missing_reason=None,
        rss=None,
        rss_lre=None,
    )


def test_summary_names_the_worst_dataset_and_lists_non_converged(nt: ModuleType) -> None:
    cells = [
        _cell(nt, "Misra1a", "lmfit", 9.0, True),
        _cell(nt, "MGH09", "lmfit", 2.5, False, termination="ier=5: max evaluations"),
        _cell(nt, "Bennett5", "lmfit", None, None, termination=None, error="ValueError: boom"),
        _cell(nt, "Misra1a", "scipy_trf", 8.0, True),
    ]
    (lm, trf) = nt.summarise_start("START1", cells, ["lmfit", "scipy_trf"])
    assert (lm.worst_param_lre, lm.dataset, lm.parameter) == (2.5, "MGH09", "b1")
    assert lm.not_converged == [{"dataset": "MGH09", "termination": "ier=5: max evaluations"}]
    assert lm.no_result == [{"dataset": "Bennett5", "error": "ValueError: boom"}]
    assert (trf.worst_param_lre, trf.dataset) == (8.0, "Misra1a")
    assert trf.not_converged == []


# ---------------------------------------------------------------- scipy standard errors


def test_scipy_stderr_matches_the_linear_least_squares_formula(nt: ModuleType) -> None:
    rng = np.random.default_rng(7)
    jac = rng.normal(size=(30, 3))
    rss = 2.5
    want = np.sqrt(np.diag(np.linalg.inv(jac.T @ jac)) * rss / (30 - 3))
    got = nt.stderr_from_jacobian(jac, rss, ["b1", "b2", "b3"])
    for name, w in zip(["b1", "b2", "b3"], want, strict=True):
        assert math.isclose(got[name], w, rel_tol=1e-10)


def test_scipy_stderr_without_degrees_of_freedom_is_none(nt: ModuleType) -> None:
    got = nt.stderr_from_jacobian(np.ones((2, 2)), 1.0, ["b1", "b2"])
    assert got == {"b1": None, "b2": None}
