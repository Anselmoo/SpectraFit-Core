"""Domain exception taxonomy: hierarchy, backward compatibility, and reach.

The taxonomy exists so a caller can catch "anything this package raised" with a
single clause. Every domain error therefore derives from *both* a package base
class and the closest builtin, so pre-existing ``except ValueError`` callers —
and the 39 ``pytest.raises(ValueError)`` assertions already in this suite —
keep working unchanged.
"""

from __future__ import annotations

import pytest
from oracles.exceptions import (
    AuditError,
    BackendError,
    BackendUnavailableError,
    CaseSpecError,
    ContractError,
    OracleError,
    RegistryError,
    UnknownKeyError,
)
from spectrafit_core.exceptions import SpecificationError, SpectraFitError


class TestSpectraFitCoreTaxonomy:
    """`spectrafit_core.exceptions` hierarchy and builtin compatibility."""

    def test_specification_error_is_a_value_error(self) -> None:
        assert issubclass(SpecificationError, ValueError)

    def test_specification_error_is_a_package_error(self) -> None:
        assert issubclass(SpecificationError, SpectraFitError)

    def test_package_base_is_not_a_value_error(self) -> None:
        # The base must stay catchable without also catching every ValueError.
        assert not issubclass(SpectraFitError, ValueError)

    def test_legacy_except_value_error_still_catches(self) -> None:
        with pytest.raises(ValueError, match="boom"):
            raise SpecificationError("boom")

    def test_exported_from_package_root(self) -> None:
        import spectrafit_core

        assert spectrafit_core.SpectraFitError is SpectraFitError
        assert spectrafit_core.SpecificationError is SpecificationError
        assert "SpectraFitError" in spectrafit_core.__all__
        assert "SpecificationError" in spectrafit_core.__all__


class TestOraclesTaxonomy:
    """`oracles.exceptions` hierarchy and builtin compatibility."""

    @pytest.mark.parametrize(
        ("exc", "builtin"),
        [
            (RegistryError, ValueError),
            (UnknownKeyError, KeyError),
            (ContractError, ValueError),
            (CaseSpecError, ValueError),
            (BackendError, ValueError),
            (BackendUnavailableError, RuntimeError),
            (AuditError, ValueError),
        ],
    )
    def test_derives_from_closest_builtin(
        self, exc: type[Exception], builtin: type[Exception]
    ) -> None:
        assert issubclass(exc, builtin)

    @pytest.mark.parametrize(
        "exc",
        [
            RegistryError,
            UnknownKeyError,
            ContractError,
            CaseSpecError,
            BackendError,
            BackendUnavailableError,
            AuditError,
        ],
    )
    def test_derives_from_package_base(self, exc: type[Exception]) -> None:
        assert issubclass(exc, OracleError)

    def test_package_base_is_not_a_builtin_subclass(self) -> None:
        assert not issubclass(OracleError, ValueError)
        assert not issubclass(OracleError, KeyError)

    def test_one_clause_catches_every_domain_error(self) -> None:
        for exc in (RegistryError, ContractError, CaseSpecError, AuditError):
            with pytest.raises(OracleError):
                raise exc("boom")


class TestRaiseSitesUseTheTaxonomy:
    """The non-validator raise sites now raise domain types, not bare builtins.

    Only sites whose exception actually reaches the caller are covered. Raises
    inside a Pydantic validator are deliberately left as plain ``ValueError``:
    Pydantic wraps them into ``ValidationError`` and discards the original type,
    so a domain type there would be inert.
    """

    def test_unknown_model_lookup(self) -> None:
        from oracles.models import get_model

        with pytest.raises(UnknownKeyError, match="unknown model"):
            get_model("no-such-model")

    def test_unknown_landscape_lookup(self) -> None:
        from oracles.opt_func import get_landscape

        with pytest.raises(UnknownKeyError, match="unknown landscape"):
            get_landscape("no-such-landscape")

    def test_unknown_model_lookup_still_catchable_as_key_error(self) -> None:
        from oracles.models import get_model

        with pytest.raises(KeyError):
            get_model("no-such-model")

    def test_missing_migration_path(self) -> None:
        from oracles.migrate import migrate_report

        with pytest.raises(ContractError, match="No migration path"):
            migrate_report({}, from_v="2.0", to_v="3.0")

    def test_missing_migration_path_still_catchable_as_value_error(self) -> None:
        from oracles.migrate import migrate_report

        with pytest.raises(ValueError, match="No migration path"):
            migrate_report({}, from_v="2.0", to_v="3.0")

    def test_compose_bind_rejects_malformed_target(self) -> None:
        from spectrafit_core import compose, gaussian

        builder = compose([gaussian(id="g", a=1.0, c=0.0, s=1.0)])
        with pytest.raises(SpecificationError, match="'node_id.param'"):
            builder.bind("g.sigma", to="g_only")

    @pytest.mark.parametrize("method", ["fit", "fit_all_slices"])
    def test_global_fit_dataset_count_mismatch(self, method: str) -> None:
        """Both GlobalFitGraph entry points must raise the domain type.

        Regression guard for a real defect: `fit` was converted to
        `SpecificationError` while `fit_all_slices` kept a bare `ValueError`
        despite its docstring promising otherwise. The pre-existing test in
        test_global_fit.py asserts `ValueError`, which `SpecificationError`
        satisfies by subclassing — so it passed either way and could not
        catch the drift. Asserting the domain type is what closes that gap.
        """
        import numpy as np
        from spectrafit_core import (
            GlobalFitGraph,
            MeasurementData,
            ModelNodeSpec,
            ModelType,
            Parameter,
        )

        g = GlobalFitGraph(
            global_nodes=[],
            local_nodes=[
                ModelNodeSpec(
                    id="bg",
                    model_type=ModelType.CONSTANT,
                    parameters={"c": Parameter(value=0.0)},
                )
            ],
            n_slices=3,
        )
        x = np.linspace(0.0, 1.0, 20)
        d = MeasurementData(x=x.tolist(), y=np.zeros_like(x).tolist())
        with pytest.raises(SpecificationError, match="expects 3 datasets, got 2"):
            getattr(g, method)([d, d])
