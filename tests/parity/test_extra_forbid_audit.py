"""Code-level audit that every Pydantic BaseModel forbids extras (Cycle 18).

Closes the audit gap surfaced in `scripts/audit_bindings.py`: the script
recommended grep-checking for `extra="forbid"` on every model, but a runtime
import + introspection check is stricter (catches subclasses whose
ConfigDict merges away the forbid) and stays in sync without a regex.

The contract this test pins:

* Every concrete `BaseModel` subclass defined under
  ``python/spectrafit_core/`` AND ``python/extras/bench/`` carries
  ``model_config["extra"] == "forbid"``.

* `extra="forbid"` is what makes the wire-format contract tight — a Rust
  field rename that the Python side missed surfaces as a `ValidationError`
  at the boundary, not as a silently-dropped field. The existing CLAUDE.md
  pydantic-first rule and the `enforce-pydantic-native` hook codify this
  at code-review time; this test is the durable runtime gate.

Exemptions: a small known-set of helper Base classes (like ``_Base`` in
``contract.py``) inherit the config from a parent. The test reports both
the model name and its resolved config so any new exception requires an
explicit allow-list entry — preventing silent drift.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Iterator

import pytest
from pydantic import BaseModel


# Modules that are NOT expected to be imported recursively (they may not
# import cleanly without optional extras, contain a __main__ guard, or be
# pure-data fixture modules).
_SKIP_MODULES: frozenset[str] = frozenset(
    {
        "oracles.nist_strd.gauss1",
        "oracles.nist_strd.gauss2",
        "oracles.nist_strd.gauss3",
        "oracles.nist_strd.lanczos1",
        "oracles.nist_strd",
    }
)

# Names known to inherit `extra="forbid"` via a parent's model_config but
# whose own `model_config` does not redeclare it. They still REJECT extras
# at runtime (verified by Pydantic via MRO resolution); the test asserts
# the *resolved* config, so they pass without needing an exemption.
_ALLOWED_NO_FORBID: frozenset[str] = frozenset(
    {
        # Add here only after manual review of why the model legitimately
        # accepts extras (e.g., a passthrough wrapper around external JSON).
    }
)


def _iter_concrete_models(package_path: str) -> Iterator[tuple[str, type[BaseModel]]]:
    """Yield ``(qualname, cls)`` for every concrete BaseModel subclass."""
    pkg = importlib.import_module(package_path)
    pkg_file = pkg.__file__
    assert pkg_file is not None
    pkg_root = pkg.__path__

    for finder, name, is_pkg in pkgutil.walk_packages(
        pkg_root, prefix=f"{package_path}."
    ):
        # Skip private cache modules + known-bad fixture loaders.
        if "__pycache__" in name or name in _SKIP_MODULES:
            continue
        try:
            module = importlib.import_module(name)
        except (ImportError, ModuleNotFoundError):
            # Optional-extra-gated modules (e.g., jax, fastapi) — skip cleanly.
            continue
        for member_name, member in inspect.getmembers(module, inspect.isclass):
            if not issubclass(member, BaseModel) or member is BaseModel:
                continue
            # Only emit the model from its DEFINING module (avoid double-counting
            # re-exports).
            if getattr(member, "__module__", None) != name:
                continue
            yield f"{name}.{member_name}", member


def _models() -> list[tuple[str, type[BaseModel]]]:
    """All BaseModel subclasses under spectrafit_core + oracles."""
    discovered: list[tuple[str, type[BaseModel]]] = []
    for pkg in ("spectrafit_core", "oracles"):
        discovered.extend(_iter_concrete_models(pkg))
    return discovered


def test_audit_discovered_models_is_nonempty() -> None:
    """Sanity: the discovery walk finds the expected core models."""
    found = {qualname for qualname, _ in _models()}
    # A non-exhaustive sample — these MUST be in the discovered set or the
    # walker has regressed and the rest of this test file is meaningless.
    expected_sample = {
        "spectrafit_core.options.FitOptions",
        "spectrafit_core.data.MeasurementData",
        "spectrafit_core.parameters.Parameter",
        "spectrafit_core.graph.FitGraph",
        "spectrafit_core.result.FitResult",
        "oracles.bench_contract.BenchReport",
    }
    missing = expected_sample - found
    assert not missing, f"audit walker missed expected models: {missing}"


def test_every_pydantic_model_forbids_extras() -> None:
    """Every concrete BaseModel under spectrafit_core + benchmark rejects
    unexpected fields.

    The test reads the *resolved* `model_config["extra"]` (Pydantic walks
    the MRO), so a model that inherits `extra="forbid"` from a parent's
    `ConfigDict` passes without redeclaring it.
    """
    offenders: list[str] = []
    for qualname, model_cls in _models():
        if qualname in _ALLOWED_NO_FORBID:
            continue
        resolved_extra = model_cls.model_config.get("extra")
        if resolved_extra != "forbid":
            offenders.append(f"{qualname} -> extra={resolved_extra!r}")
    assert not offenders, (
        "Pydantic models missing extra='forbid' (a silent-drift risk):\n  "
        + "\n  ".join(offenders)
    )


def test_fit_options_rejects_invalid_bounds() -> None:
    """Cycle 18: FitOptions numeric fields enforce sensible bounds."""
    from spectrafit_core import FitOptions

    # max_iterations >= 1
    with pytest.raises(ValueError):
        FitOptions(max_iterations=0)
    # tolerance >= 0 (zero means "use solver default" per the docstring)
    FitOptions(tolerance=0.0)  # OK
    with pytest.raises(ValueError):
        FitOptions(tolerance=-1.0)
    # delta0/max_delta > 0 (a zero trust-region radius blocks progress)
    with pytest.raises(ValueError):
        FitOptions(delta0=0.0)
    with pytest.raises(ValueError):
        FitOptions(max_delta=-1.0)
    # eta in [0, 1)
    with pytest.raises(ValueError):
        FitOptions(eta=1.0)
    with pytest.raises(ValueError):
        FitOptions(eta=-0.1)
    # Smoke: the defaults are still valid.
    FitOptions()  # OK
