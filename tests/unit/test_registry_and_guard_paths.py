"""Cover the guard and degradation paths the happy-path suite never reaches.

These are the branches that only fire when something has gone wrong — a
duplicate registration, an absent optional dependency, a backend that raises.
They are the least-exercised code in the package and among the most
consequential, because each one decides how a failure is *reported*. A silent
`pass` in the wrong place is how an optional backend disappears from a
benchmark without anyone noticing, which is exactly what happened to the JAX
backend before its kernels were ported.

Every test here pins a behaviour with a stated reason, not a line number.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from oracles.exceptions import RegistryError


class TestRegistryDuplicateGuards:
    """Registering the same key twice must raise, never silently overwrite.

    `CLAUDE.md`'s registry-over-map rule means these dicts are the single source
    of truth for which shapes and landscapes exist. A silent overwrite would let
    a later import replace a kernel with a different implementation under the
    same name, and every downstream consumer — the benchmark registry, the case
    recipes, the parity tests — would keep using the name believing it meant the
    first thing.
    """

    def test_duplicate_lineshape_key_raises(self) -> None:
        """A second `register_lineshape` under one key is a hard error."""
        from oracles.lineshapes import LINESHAPE_RECIPE_REGISTRY, register_lineshape

        key = "_dup_probe_lineshape"
        assert key not in LINESHAPE_RECIPE_REGISTRY

        @register_lineshape(key)
        def _first(rng: Any, variant: str) -> tuple[list[Any], str]:
            return [], variant

        try:
            with pytest.raises(RegistryError, match=key):

                @register_lineshape(key)
                def _second(rng: Any, variant: str) -> tuple[list[Any], str]:
                    return [], variant

        finally:
            # The registry is module-global; leaving the probe behind would leak
            # into any later test that enumerates it.
            LINESHAPE_RECIPE_REGISTRY.pop(key, None)

    def test_duplicate_landscape_key_raises(self) -> None:
        """Same guard on the optimisation-landscape registry."""
        from oracles.opt_func import LANDSCAPE_REGISTRY, register_landscape

        key = "_dup_probe_landscape"
        assert key not in LANDSCAPE_REGISTRY

        @register_landscape(key)
        def _first(x: Any) -> Any:
            return x

        try:
            with pytest.raises(RegistryError, match=key):

                @register_landscape(key)
                def _second(x: Any) -> Any:
                    return x

        finally:
            LANDSCAPE_REGISTRY.pop(key, None)


class TestBackendFailureIsReportedNotFatal:
    """A raising backend must be logged and skipped, not allowed to sink the run."""

    def test_safe_fit_returns_none_and_logs_on_exception(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """`_safe_fit` swallows the exception but leaves evidence.

        The swallow is deliberate — one bad fit among 151 cases should not abort
        the suite. The log line is what stops that from becoming silent: without
        it a systematically broken backend is indistinguishable from one whose
        cases were all unsupported, which reads on the report as "not
        applicable" rather than "broken".
        """
        from oracles._engine_base import _safe_fit

        class _Exploding:
            name = "exploding"

            def is_supported(self, case: Any) -> bool:
                return True

            def fit(self, case: Any, n_reps: int) -> Any:
                msg = "kaboom"
                raise RuntimeError(msg)

        class _Case:
            id = "CASE-042"

        with caplog.at_level(logging.WARNING):
            out = _safe_fit(_Exploding(), _Case(), n_reps=1)

        assert out is None
        assert "exploding" in caplog.text, "backend name must reach the log"
        assert "CASE-042" in caplog.text, "case id must reach the log"
        assert "kaboom" in caplog.text, "the original exception must not be swallowed silently"

    def test_safe_fit_returns_none_for_unsupported_case_without_logging(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """An unsupported case is not a failure and must not be logged as one.

        This is the distinction the log exists to preserve: `None` from
        unsupported and `None` from broken are the same return value, so only
        the absence of a warning separates them.
        """
        from oracles._engine_base import _safe_fit

        class _Unsupported:
            name = "picky"

            def is_supported(self, case: Any) -> bool:
                return False

            def fit(self, case: Any, n_reps: int) -> Any:  # pragma: no cover
                msg = "must not be called"
                raise AssertionError(msg)

        class _Case:
            id = "CASE-043"

        with caplog.at_level(logging.WARNING):
            assert _safe_fit(_Unsupported(), _Case(), n_reps=1) is None
        assert caplog.text == ""


class TestEmptyInputEdgeCases:
    """Degenerate inputs return empty results rather than raising."""

    def test_ecdf_of_empty_is_empty(self) -> None:
        """An empty sample has no empirical CDF; `[]` beats a ZeroDivisionError."""
        from oracles.metrics import ecdf

        assert ecdf([]) == []

    def test_ecdf_is_monotone_and_reaches_one(self) -> None:
        """Guard the non-empty path too, so the empty case is not the only pin."""
        from oracles.metrics import ecdf

        pts = ecdf([3.0, 1.0, 2.0])
        assert [p.x for p in pts] == [1.0, 2.0, 3.0], "must sort ascending"
        assert [p.y for p in pts] == pytest.approx([1 / 3, 2 / 3, 1.0])


class TestSpectrafitCoreValidation:
    """Public-API validation paths."""

    def test_unknown_model_name_raises_rather_than_resolving(self) -> None:
        """An unrecognised model name must not resolve to anything.

        `ModelType._missing_` returns None for an unknown string, which makes
        Python's Enum machinery raise. That is the desired end state: a typo in a
        model name should fail at the boundary, not produce a null that some
        later `match` treats as a default branch.
        """
        from spectrafit_core.models import ModelType

        with pytest.raises(ValueError, match="definitely-not-a-model"):
            ModelType("definitely-not-a-model")

    def test_model_name_lookup_is_case_insensitive(self) -> None:
        """`_missing_` lowercases before comparing, so wire casing cannot matter.

        The JSON boundary carries these names as free strings; a producer that
        emits "GAUSSIAN" must reach the same member as one emitting "gaussian",
        or the Rust and Python sides disagree about a model they both support.
        """
        from spectrafit_core.models import ModelType

        assert ModelType("GAUSSIAN") is ModelType.GAUSSIAN
        assert ModelType("GaUsSiAn") is ModelType.GAUSSIAN
        assert ModelType("gaussian") is ModelType.GAUSSIAN

    def test_negative_dataset_index_is_rejected(self) -> None:
        """`dataset_index` addresses a list position, so negatives are invalid.

        Python would silently accept -1 as "last dataset", which is a plausible
        and completely wrong reading in a multi-dataset fit.
        """
        from spectrafit_core.models import ModelNodeSpec

        with pytest.raises(ValueError, match="non-negative"):
            ModelNodeSpec(
                id="n1",
                model_type="gaussian",
                dataset_index=-1,
                parameters={},
            )
