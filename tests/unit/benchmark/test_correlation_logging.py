"""EF-PY-12 regression: _correlation must LOG its silent covariance failure.

When the inner spectrafit fit/covariance call inside ``_correlation`` raises an
Exception, the function correctly returns ``[]`` (covariance is optional and must
not sink the run). BUT the failure was previously swallowed silently — the bare
``except Exception: return []`` emitted no log record, making a systematically
broken covariance path indistinguishable from a case that genuinely has no
correlation (e.g. ``_HAS_SPECTRAFIT`` is False).

This test pins the corrected contract:
- ``_correlation`` still returns ``[]`` on failure (behavior preserved).
- A WARNING is logged that mentions the failure (visibility restored).
"""

from __future__ import annotations

import logging

import pytest

from oracles.engine import _correlation
from oracles.cases import BenchCase, build_catalog, featured_case


@pytest.fixture()
def featured() -> object:
    """The featured BenchCase — the same input _correlation receives in production."""
    return featured_case(build_catalog())


def test_correlation_logs_on_covariance_failure(
    featured: object,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_correlation logs a WARNING when the inner fit raises, and still returns [].

    EF-PY-12: silent failure — a bare ``except Exception: return []`` emitted no
    log record.  The fix: log before returning so a systematically broken covariance
    path is visible in the run output.
    """
    # Force the build step to raise so we reach the except branch.
    # Patching SpectraFitBackend.build is the earliest surface inside the try block
    # that is independent of the actual spectrafit_core fit call.
    import oracles.backends._spectrafit as _sf_mod

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected covariance failure (EF-PY-12 test)")

    monkeypatch.setattr(_sf_mod.SpectraFitBackend, "build", _boom)

    assert isinstance(featured, BenchCase)
    bench_case: BenchCase = featured
    with caplog.at_level(logging.WARNING, logger="oracles.engine"):
        result = _correlation(bench_case)

    # (a) behavior preserved: still returns []
    assert result == [], (
        f"Expected [] on covariance failure, got {result!r}. "
        "_correlation must not crash when the inner fit raises."
    )

    # (b) visibility restored: a WARNING must be logged
    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_records, (
        "No WARNING was emitted when _correlation's inner fit raised. "
        "EF-PY-12: silent failure must become a visible log record."
    )
    # The message should mention correlation or covariance so it is diagnosable
    combined = " ".join(r.getMessage() for r in warning_records).lower()
    assert "corr" in combined or "cov" in combined, (
        f"WARNING message does not mention 'corr' or 'cov': {combined!r}. "
        "The log message must make the failure context clear."
    )
