"""Tests for :meth:`FitResult.explain` — narrative lab-notebook summary.

The :meth:`explain` method emits 4–6 sentences of interpretive prose, anchored
on existing fields (no new state). These tests assert:

* presence of expected keywords ("converged", "iterations", "χ²"),
* the goodness/conditioning verdicts respect their numerical anchors,
* the numbers spoken in prose match the source fields (regex-extract +
  ``numpy.testing.assert_allclose``),
* parametrised coverage over success/fail, condition-number present/absent,
  and multiple peaks (largest amplitude wins).
"""

from __future__ import annotations

import re

import numpy as np
import pytest
from numpy.testing import assert_allclose

from spectrafit_core import FitResult, ParameterResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    *,
    success: bool = True,
    n_iter: int = 12,
    message: str = "converged",
    reduced_chi2: float = 1.0,
    condition_number: float | None = None,
    aic: float = 0.0,
    parameters: dict[str, ParameterResult] | None = None,
) -> FitResult:
    """Build a synthetic FitResult mirroring the contract."""
    return FitResult(
        success=success,
        n_iter=n_iter,
        message=message,
        reduced_chi2=reduced_chi2,
        condition_number=condition_number,
        aic=aic,
        parameters=parameters or {},
    )


_NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"


def _extract_floats(prose: str) -> list[float]:
    """Pull every numeric token (incl. scientific notation) out of the prose."""
    return [float(m) for m in re.findall(_NUM, prose)]


def _sentences(prose: str) -> list[str]:
    """Split prose into sentences on ``". "`` so decimals stay intact."""
    parts = re.split(r"\.\s+", prose.strip())
    # The final sentence may keep its trailing period; that's fine.
    return [p for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Keyword presence (per task spec)
# ---------------------------------------------------------------------------


def test_explain_returns_a_nonempty_string() -> None:
    prose = _make_result().explain()
    assert isinstance(prose, str)
    assert prose.strip()


def test_explain_mentions_convergence_keywords() -> None:
    prose = _make_result(success=True, n_iter=7).explain()
    assert "Converged" in prose
    assert "iterations" in prose


def test_explain_mentions_chi_squared_keyword() -> None:
    prose = _make_result().explain()
    assert "χ²" in prose


def test_explain_sentence_count_in_window() -> None:
    """Without optional lines we expect 2 sentences; with all 5 we expect 5."""
    minimal = _make_result().explain()
    minimal_sentences = _sentences(minimal)
    assert 2 <= len(minimal_sentences) <= 6

    rich = _make_result(
        condition_number=42.0,
        aic=12.3,
        parameters={
            "g.amplitude": ParameterResult(value=2.0, stderr=0.1, name="g.amplitude"),
            "g.center": ParameterResult(value=0.5, stderr=0.05, name="g.center"),
        },
    ).explain()
    rich_sentences = _sentences(rich)
    assert 4 <= len(rich_sentences) <= 6


# ---------------------------------------------------------------------------
# Success vs failure (parametrised)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("success", "n_iter", "message", "expected_token"),
    [
        (True, 12, "ok", "Converged in 12 iterations"),
        (False, 200, "max iterations reached", "Failed to converge"),
        (False, 200, "", "no message reported"),
    ],
)
def test_explain_convergence_line(
    success: bool, n_iter: int, message: str, expected_token: str
) -> None:
    prose = _make_result(success=success, n_iter=n_iter, message=message).explain()
    assert expected_token in prose
    if not success and message:
        assert message in prose


def test_explain_failure_reports_iteration_count() -> None:
    prose = _make_result(success=False, n_iter=200, message="stalled").explain()
    # The first sentence should contain the iteration count exactly.
    first_sentence = _sentences(prose)[0]
    assert "200" in first_sentence


# ---------------------------------------------------------------------------
# Goodness-of-fit anchors (match/case dispatch in the implementation)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rchi2", "expected_phrase"),
    [
        (0.1, "overfitting"),
        (1.0, "good fit"),
        (1.4, "good fit"),
        (2.0, "moderate misfit"),
        (5.0, "poor fit"),
    ],
)
def test_explain_goodness_verdicts(rchi2: float, expected_phrase: str) -> None:
    prose = _make_result(reduced_chi2=rchi2).explain()
    assert expected_phrase in prose


def test_explain_reduced_chi2_value_appears_in_prose() -> None:
    rchi2 = 2.345
    prose = _make_result(reduced_chi2=rchi2).explain()
    # Find the χ² sentence and verify the number is the formatted reduced_chi2.
    chi_sentence = next(s for s in _sentences(prose) if "χ²" in s)
    floats = _extract_floats(chi_sentence)
    assert floats, "expected at least one number in the χ² sentence"
    assert_allclose(floats[0], rchi2, rtol=0.01)


# ---------------------------------------------------------------------------
# Conditioning anchors (optional line)
# ---------------------------------------------------------------------------


def test_explain_omits_conditioning_when_absent() -> None:
    prose = _make_result(condition_number=None).explain()
    assert "κ" not in prose
    assert "conditioned" not in prose


@pytest.mark.parametrize(
    ("kappa", "expected_phrase"),
    [
        (23.0, "well-conditioned"),
        (5e4, "acceptably conditioned"),
        (1e9, "ill-conditioned"),
    ],
)
def test_explain_conditioning_verdicts(kappa: float, expected_phrase: str) -> None:
    prose = _make_result(condition_number=kappa).explain()
    assert expected_phrase in prose
    assert "κ" in prose


def test_explain_kappa_value_matches_source_field() -> None:
    kappa = 1234.5
    prose = _make_result(condition_number=kappa).explain()
    kappa_sentence = next(s for s in _sentences(prose) if "κ" in s)
    floats = _extract_floats(kappa_sentence)
    assert floats, "expected at least one number in the κ sentence"
    assert_allclose(floats[-1], kappa, rtol=0.01)


# ---------------------------------------------------------------------------
# Dominant peak (parametrised over single / multiple amplitudes)
# ---------------------------------------------------------------------------


def test_explain_omits_peak_line_when_no_amplitude_parameter() -> None:
    params = {
        "g.center": ParameterResult(value=0.0, stderr=0.1, name="g.center"),
        "g.sigma": ParameterResult(value=1.0, stderr=0.05, name="g.sigma"),
    }
    prose = _make_result(parameters=params).explain()
    assert "Dominant peak" not in prose


def test_explain_picks_largest_amplitude() -> None:
    params = {
        "p1.amplitude": ParameterResult(value=1.0, stderr=0.1, name="p1.amplitude"),
        "p1.center": ParameterResult(value=0.0, stderr=0.01, name="p1.center"),
        "p2.amplitude": ParameterResult(value=5.5, stderr=0.2, name="p2.amplitude"),
        "p2.center": ParameterResult(value=3.0, stderr=0.05, name="p2.center"),
        "p3.amplitude": ParameterResult(value=2.0, stderr=0.1, name="p3.amplitude"),
        "p3.center": ParameterResult(value=-2.0, stderr=0.03, name="p3.center"),
    }
    prose = _make_result(parameters=params).explain()
    assert "p2.amplitude" in prose
    # Make sure neither of the smaller amplitudes was selected.
    assert "p1.amplitude" not in prose
    assert "p3.amplitude" not in prose


def test_explain_peak_numbers_match_parameter_fields() -> None:
    amp_val, amp_err = 5.5, 0.2
    cen_val, cen_err = 3.0, 0.05
    params = {
        "p.amplitude": ParameterResult(
            value=amp_val, stderr=amp_err, name="p.amplitude"
        ),
        "p.center": ParameterResult(value=cen_val, stderr=cen_err, name="p.center"),
    }
    prose = _make_result(parameters=params).explain()
    peak_sentence = next(s for s in _sentences(prose) if "Dominant peak" in s)
    floats = _extract_floats(peak_sentence)
    # Expect amp, amp_err, center, center_err in order.
    assert len(floats) >= 4
    assert_allclose(
        np.array(floats[:4]),
        np.array([amp_val, amp_err, cen_val, cen_err]),
        rtol=0.01,
    )


def test_explain_handles_short_amplitude_key_a() -> None:
    """A parameter ending in ``.a`` is also recognised as an amplitude."""
    params = {
        "n.a": ParameterResult(value=7.7, stderr=0.3, name="n.a"),
        "n.center": ParameterResult(value=1.1, stderr=0.02, name="n.center"),
    }
    prose = _make_result(parameters=params).explain()
    assert "Dominant peak" in prose
    assert "n.a" in prose


def test_explain_peak_without_stderr_or_center() -> None:
    params = {
        "lone.amplitude": ParameterResult(
            value=4.0, stderr=None, name="lone.amplitude"
        ),
    }
    prose = _make_result(parameters=params).explain()
    assert "Dominant peak" in prose
    # No ± when stderr missing.
    peak_sentence = next(s for s in _sentences(prose) if "Dominant peak" in s)
    assert "±" not in peak_sentence


# ---------------------------------------------------------------------------
# AIC line (optional)
# ---------------------------------------------------------------------------


def test_explain_omits_aic_when_zero() -> None:
    prose = _make_result(aic=0.0).explain()
    assert "AIC" not in prose


def test_explain_mentions_aic_when_nonzero() -> None:
    prose = _make_result(aic=42.5).explain()
    assert "AIC" in prose
    aic_sentence = next(s for s in _sentences(prose) if "AIC" in s)
    floats = _extract_floats(aic_sentence)
    assert floats
    assert_allclose(floats[0], 42.5, rtol=0.01)


# ---------------------------------------------------------------------------
# Non-finite values are handled gracefully
# ---------------------------------------------------------------------------


def test_explain_handles_nan_reduced_chi2() -> None:
    """A NaN reduced χ² (failed fit) must not be labelled as "poor fit"."""
    prose = _make_result(
        success=False, n_iter=0, message="diverged", reduced_chi2=float("nan")
    ).explain()
    assert "undefined" in prose
    assert "poor fit" not in prose
    assert "good fit" not in prose


def test_explain_handles_infinite_condition_number() -> None:
    """A non-finite κ does not get a misleading 'ill-conditioned' verdict."""
    prose = _make_result(condition_number=float("inf")).explain()
    assert "non-finite" in prose


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_explain_is_deterministic() -> None:
    """Same FitResult instance must produce identical prose across calls."""
    result = _make_result(
        condition_number=100.0,
        aic=10.0,
        parameters={
            "g.amplitude": ParameterResult(value=2.0, stderr=0.1, name="g.amplitude"),
            "g.center": ParameterResult(value=0.5, stderr=0.05, name="g.center"),
        },
    )
    a = result.explain()
    b = result.explain()
    assert a == b


# ---------------------------------------------------------------------------
# Exact match-arm boundaries (not covered by the parametrize table above)
# ---------------------------------------------------------------------------


def test_explain_boundary_0_5_maps_to_good_fit() -> None:
    """rchi2 exactly at 0.5 falls into the [0.5, 1.5) arm → 'good fit'."""
    prose = _make_result(reduced_chi2=0.5).explain()
    assert "good fit" in prose


def test_explain_boundary_1_5_maps_to_moderate_misfit() -> None:
    """rchi2 exactly at 1.5 falls into the [1.5, 3.0) arm → 'moderate misfit'."""
    prose = _make_result(reduced_chi2=1.5).explain()
    assert "moderate misfit" in prose


def test_explain_boundary_3_0_maps_to_poor_fit() -> None:
    """rchi2 exactly at 3.0 falls into the default arm → 'poor fit'."""
    prose = _make_result(reduced_chi2=3.0).explain()
    assert "poor fit" in prose


def test_explain_negative_r_squared_does_not_crash() -> None:
    """A negative r² is a legitimate poor fit — explain() must not raise."""
    result = FitResult(
        success=True,
        n_iter=5,
        message="converged",
        reduced_chi2=2.1,
        r_squared=-0.3,
    )
    prose = result.explain()
    assert isinstance(prose, str) and prose.strip()
