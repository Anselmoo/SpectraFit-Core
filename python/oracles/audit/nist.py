r"""NIST StRD certified-value validation emitter (wire W8 evidence).

Re-runs 22 of NIST's 27 StRD nonlinear-regression datasets — Gauss1, Gauss2,
Gauss3, Lanczos1, Lanczos2, Lanczos3, BoxBOD, Misra1a, Misra1b, MGH17,
Bennett5, MGH09, Eckerle4, Roszman1, DanWood, Kirby2, Hahn1, Thurber, Rat42,
Rat43, Chwirut1, Chwirut2 — and returns a structured
:class:`~oracles.trust_ledger.NistValidation`. The original ten also have a
dedicated scenario test apiece under ``tests/scenario/nist_strd/``; the
remaining twelve are exercised here and via kernel-correctness numpy-oracle
tests only. Each fit starts from NIST's published START2 guess, recovers the
parameters via spectrafit's LM solver, projects them back to the NIST
parameterization, and records the significant-figure agreement against the
certified values.

The fits are tiny ($\leq$ 250 points, ~0.4 s total) and deterministic; this is the
cheap, independent external-replication oracle that earns the honest RUNG_5.

The build/project recipes intentionally mirror the scenario tests' ``_build_graph``
/ ``_project_to_nist`` helpers verbatim (same parameterization mapping, same
START2 guess) so this emitter and the green scenario tests assert the same fit.

**Bennett5 note:** Bennett5 is NIST "Higher" difficulty and may not converge to
the certified values from START2 via the LM solver.  Its ``_NistRecipe`` entry
is included for completeness; if it does not pass the sig-fig threshold the
``NistDataset.passed`` flag will be ``False`` for that entry.  ``NistValidation.passed``
is a strict ``all()`` over every recipe dataset with **no exclusion in this
production path** — a Bennett5 regression fails the overall validation and caps
the W8 wire (and therefore the RUNG_5 unlock) exactly like any other dataset
would. The unit test suite (``tests/audit/test_nist_validation.py``) separately
tracks a narrower ``_OPTIONAL_DATASETS`` subset for its own "mandatory datasets
pass" assertion, but that exclusion is local to the test and is never applied
to the value this module (or the W8 wire) actually returns.

**MGH09 note:** MGH09 is also NIST "Higher" difficulty (Kowalik–Osborne rational
function).  It is included for kernel-correctness evidence (the ``MGH09_RATIONAL``
kernel and parity oracle are verified), but LM-solver convergence to the certified
values is not guaranteed from either NIST start.  Like Bennett5, it is in the test
suite's ``_OPTIONAL_DATASETS`` set, not excluded from this module's own
``NistValidation.passed``.

**Threshold & denominator:** ``NIST_SIGFIG_THRESHOLD`` (4.0) is the minimum
significant-figure agreement required for a dataset to "pass". The scenario
tests assert 1e-3 relative (~3 sig figs) on parameters; this emitter holds
to the stricter $\ge$4 sig figs (1e-4 relative) that the RSS/$\chi^2$
assertions use, which the actual fits clear by ~6 figures of headroom.
``NIST_STRD_TOTAL`` (27) is the size of the external NIST StRD
nonlinear-regression universe (Lower/Average/Higher difficulty) — the
canonical denominator for "N of M datasets reproduced"
(https://www.itl.nist.gov/div898/strd/nls/nls_main.shtml). It lives here
(the validation source of truth) and is emitted on the contract so the UI
never hardcodes it.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict
from spectrafit_core import (
    FitGraph,
    FitOptions,
    FitResult,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

from oracles.nist_strd import (
    bennett5,
    boxbod,
    chwirut1,
    chwirut2,
    danwood,
    eckerle4,
    gauss1,
    gauss2,
    gauss3,
    hahn1,
    kirby2,
    lanczos1,
    lanczos2,
    lanczos3,
    mgh09,
    mgh17,
    misra1a,
    misra1b,
    rat42,
    rat43,
    roszman1,
    thurber,
)
from oracles.trust_ledger import NistDataset, NistParam, NistValidation

NIST_SIGFIG_THRESHOLD = 4.0

NIST_STRD_TOTAL = 27

SQRT2 = math.sqrt(2.0)

_SIGFIG_CAP = 15.0
"""Info:
    Cap for sig-fig agreement when the recovered value is bit-identical to the
    certified one (rel == 0); avoids a +inf that would not serialize to JSON.
"""

_LM_OPTS = FitOptions(solver="lm", max_iterations=10000, tolerance=1e-12)


def _sig_figs(fitted: float, certified: float) -> float:
    """-log10(|fitted-certified|/|certified|), capped for exact agreement."""
    denom = abs(certified)
    # Lanczos1-style machine-epsilon certified value: fall back to absolute.
    rel = abs(fitted - certified) if denom == 0.0 else abs(fitted - certified) / denom
    if rel <= 0.0:
        return _SIGFIG_CAP
    return min(_SIGFIG_CAP, -math.log10(rel))


# --- Shared builders: NIST → spectrafit FitGraph (verbatim from scenario tests).


def _build_two_gaussian_graph(start: dict[str, float]) -> FitGraph:
    r"""One DoubleExponential (A2=0 fixed) + two Gaussians ($\sigma = b/\sqrt{2}$).

    Shared by Gauss1/2/3 — identical model, only data + certified values differ.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="exp",
                model_type=ModelType.DOUBLE_EXPONENTIAL,
                parameters={
                    "A1": Parameter(value=start["b1"]),
                    "lam1": Parameter(value=start["b2"], min=0.0),
                    "A2": Parameter(value=0.0, vary=False),
                    "lam2": Parameter(value=1.0, vary=False),
                },
            ),
            ModelNodeSpec(
                id="g1",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=start["b3"], min=0.0),
                    "center": Parameter(value=start["b4"]),
                    "sigma": Parameter(value=start["b5"] / SQRT2, min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="g2",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=start["b6"], min=0.0),
                    "center": Parameter(value=start["b7"]),
                    "sigma": Parameter(value=start["b8"] / SQRT2, min=1e-3),
                },
            ),
        ],
    )


def _project_two_gaussian(result: FitResult) -> dict[str, float]:
    p = result.params
    return {
        "b1": p["exp.A1"].value,
        "b2": p["exp.lam1"].value,
        "b3": p["g1.amplitude"].value,
        "b4": p["g1.center"].value,
        "b5": p["g1.sigma"].value * SQRT2,
        "b6": p["g2.amplitude"].value,
        "b7": p["g2.center"].value,
        "b8": p["g2.sigma"].value * SQRT2,
    }


def _build_lanczos_graph(start: dict[str, float]) -> FitGraph:
    """Two DoubleExponential nodes covering three pure-exponential terms."""
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="exp12",
                model_type=ModelType.DOUBLE_EXPONENTIAL,
                parameters={
                    "A1": Parameter(value=start["b1"], min=0.0),
                    "lam1": Parameter(value=start["b2"], min=0.0),
                    "A2": Parameter(value=start["b3"], min=0.0),
                    "lam2": Parameter(value=start["b4"], min=0.0),
                },
            ),
            ModelNodeSpec(
                id="exp3",
                model_type=ModelType.DOUBLE_EXPONENTIAL,
                parameters={
                    "A1": Parameter(value=start["b5"], min=0.0),
                    "lam1": Parameter(value=start["b6"], min=0.0),
                    "A2": Parameter(value=0.0, vary=False),
                    "lam2": Parameter(value=1.0, vary=False),
                },
            ),
        ],
    )


def _project_lanczos(result: FitResult) -> dict[str, float]:
    p = result.params
    return {
        "b1": p["exp12.A1"].value,
        "b2": p["exp12.lam1"].value,
        "b3": p["exp12.A2"].value,
        "b4": p["exp12.lam2"].value,
        "b5": p["exp3.A1"].value,
        "b6": p["exp3.lam1"].value,
    }


def _build_boxbod_graph(start: dict[str, float]) -> FitGraph:
    """Single SATURATING_EXPONENTIAL node for the NIST BoxBOD model.

    amplitude = b1, rate = b2 — 1-to-1 mapping, no re-parameterization.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="bod",
                model_type=ModelType.SATURATING_EXPONENTIAL,
                parameters={
                    "amplitude": Parameter(value=start["b1"], min=0.0),
                    "rate": Parameter(value=start["b2"], min=0.0),
                },
            ),
        ],
    )


def _project_boxbod(result: FitResult) -> dict[str, float]:
    p = result.params
    return {
        "b1": p["bod.amplitude"].value,
        "b2": p["bod.rate"].value,
    }


def _build_misra1a_graph(start: dict[str, float]) -> FitGraph:
    """Single SATURATING_EXPONENTIAL node for the NIST Misra1a model.

    amplitude = b1, rate = b2 — 1-to-1 mapping, no re-parameterization.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="m1a",
                model_type=ModelType.SATURATING_EXPONENTIAL,
                parameters={
                    "amplitude": Parameter(value=start["b1"], min=0.0),
                    "rate": Parameter(value=start["b2"], min=0.0),
                },
            ),
        ],
    )


def _project_misra1a(result: FitResult) -> dict[str, float]:
    p = result.params
    return {
        "b1": p["m1a.amplitude"].value,
        "b2": p["m1a.rate"].value,
    }


def _build_misra1b_graph(start: dict[str, float]) -> FitGraph:
    """Single POWER_SATURATION node for the NIST Misra1b model.

    amplitude = b1, rate = b2 — 1-to-1 mapping, no re-parameterization.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="m1b",
                model_type=ModelType.POWER_SATURATION,
                parameters={
                    "amplitude": Parameter(value=start["b1"], min=0.0),
                    "rate": Parameter(value=start["b2"], min=0.0),
                },
            ),
        ],
    )


def _project_misra1b(result: FitResult) -> dict[str, float]:
    p = result.params
    return {
        "b1": p["m1b.amplitude"].value,
        "b2": p["m1b.rate"].value,
    }


def _build_mgh17_graph(start: dict[str, float]) -> FitGraph:
    r"""Constant + DoubleExponential for NIST MGH17 (Osborne 1).

    Node ``bg`` carries the constant offset b1; node ``exp`` carries the two
    exponential decay terms $b2 \cdot \exp(-b4 \cdot x) + b3 \cdot \exp(-b5 \cdot x)$.  b3 < 0 in the
    certified solution so A2 has no lower bound.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="bg",
                model_type=ModelType.CONSTANT,
                parameters={
                    "c": Parameter(value=start["b1"]),
                },
            ),
            ModelNodeSpec(
                id="exp",
                model_type=ModelType.DOUBLE_EXPONENTIAL,
                parameters={
                    "A1": Parameter(value=start["b2"]),
                    "lam1": Parameter(value=start["b4"], min=0.0),
                    "A2": Parameter(value=start["b3"]),
                    "lam2": Parameter(value=start["b5"], min=0.0),
                },
            ),
        ],
    )


def _project_mgh17(result: FitResult) -> dict[str, float]:
    p = result.params
    return {
        "b1": p["bg.c"].value,
        "b2": p["exp.A1"].value,
        "b3": p["exp.A2"].value,
        "b4": p["exp.lam1"].value,
        "b5": p["exp.lam2"].value,
    }


def _build_mgh09_graph(start: dict[str, float]) -> FitGraph:
    """Single MGH09_RATIONAL node for the NIST MGH09 model.

    amplitude = b1, num_lin = b2, den_lin = b3, den_const = b4 — 1-to-1 mapping.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="mgh09",
                model_type=ModelType.MGH09_RATIONAL,
                parameters={
                    "amplitude": Parameter(value=start["b1"]),
                    "num_lin": Parameter(value=start["b2"]),
                    "den_lin": Parameter(value=start["b3"]),
                    "den_const": Parameter(value=start["b4"]),
                },
            ),
        ],
    )


def _project_mgh09(result: FitResult) -> dict[str, float]:
    p = result.params
    return {
        "b1": p["mgh09.amplitude"].value,
        "b2": p["mgh09.num_lin"].value,
        "b3": p["mgh09.den_lin"].value,
        "b4": p["mgh09.den_const"].value,
    }


def _build_bennett5_graph(start: dict[str, float]) -> FitGraph:
    """Single POWER_LAW_OFFSET node for the NIST Bennett5 model.

    amplitude = b1, offset = b2, shape = b3 — 1-to-1 mapping.
    offset is bounded below at 0.1 (physical: offset+x must be positive).
    shape is bounded below at 0.01 (avoids -1/shape division-by-zero).
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="b5",
                model_type=ModelType.POWER_LAW_OFFSET,
                parameters={
                    "amplitude": Parameter(value=start["b1"]),
                    "offset": Parameter(value=start["b2"], min=0.1),
                    "shape": Parameter(value=start["b3"], min=0.01),
                },
            ),
        ],
    )


def _project_bennett5(result: FitResult) -> dict[str, float]:
    p = result.params
    return {
        "b1": p["b5.amplitude"].value,
        "b2": p["b5.offset"].value,
        "b3": p["b5.shape"].value,
    }


class _NistRecipe(BaseModel):
    """Declarative recipe for one NIST StRD dataset validation."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    name: str
    model: str
    certified: dict[str, tuple[float, float]]
    start: dict[str, float]
    build: Callable[[dict[str, float]], FitGraph]
    project: Callable[[FitResult], dict[str, float]]
    x: list[float]
    y: list[float]


def _build_eckerle4_graph(start: dict[str, float]) -> FitGraph:
    r"""One Gaussian; NIST's amplitude b1 is this kernel's ``amplitude * sigma``.

    $(b_1/b_2)\,e^{-\tfrac{1}{2}\left((x-b_3)/b_2\right)^2}$ is a Gaussian with
    ``sigma = b2`` and ``center = b3`` whose amplitude is coupled to its width. The
    coupling is carried in the projection rather than by a new kernel.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=start["b1"] / start["b2"]),
                    "center": Parameter(value=start["b3"]),
                    "sigma": Parameter(value=start["b2"], min=1e-12),
                },
            ),
        ],
    )


def _project_eckerle4(result: FitResult) -> dict[str, float]:
    p = result.params
    sigma = p["g.sigma"].value
    return {"b1": p["g.amplitude"].value * sigma, "b2": sigma, "b3": p["g.center"].value}


def _build_roszman1_graph(start: dict[str, float]) -> FitGraph:
    r"""A line plus a unit arctan step.

    $b_1 - b_2 x - \arctan\!\left(b_3/(x-b_4)\right)/\pi$ needs the arctan reciprocal
    identity, and the branch is load-bearing: on this data ``b3/(x-b4)`` is negative
    throughout, so $\arctan(z) = -\pi/2 - \arctan(1/z)$ and the $-\pi/2$ cancels
    the step's own $+\tfrac{1}{2}$ offset, leaving the intercept carrying ``b1``
    unchanged. Assuming the positive branch instead converges, reports success,
    and lands a constant away from the certified values.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="lin",
                model_type=ModelType.LINEAR,
                parameters={
                    "slope": Parameter(value=-start["b2"]),
                    "intercept": Parameter(value=start["b1"]),
                },
            ),
            ModelNodeSpec(
                id="atan",
                model_type=ModelType.ARCTAN_STEP,
                parameters={
                    "amplitude": Parameter(value=1.0, vary=False),
                    "center": Parameter(value=start["b4"]),
                    "sigma": Parameter(value=start["b3"]),
                },
            ),
        ],
    )


def _project_roszman1(result: FitResult) -> dict[str, float]:
    p = result.params
    return {
        "b1": p["lin.intercept"].value,
        "b2": -p["lin.slope"].value,
        "b3": p["atan.sigma"].value,
        "b4": p["atan.center"].value,
    }


def _build_danwood_graph(start: dict[str, float]) -> FitGraph:
    """A pure power law: ``power_law_offset`` with the offset held at zero."""
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="pw",
                model_type=ModelType.POWER_LAW_OFFSET,
                parameters={
                    "amplitude": Parameter(value=start["b1"]),
                    "offset": Parameter(value=0.0, vary=False),
                    "shape": Parameter(value=-1.0 / start["b2"]),
                },
            ),
        ],
    )


def _project_danwood(result: FitResult) -> dict[str, float]:
    p = result.params
    return {"b1": p["pw.amplitude"].value, "b2": -1.0 / p["pw.shape"].value}


def _build_rational_cubic_graph(
    start: dict[str, float],
    *,
    cubic: bool,
) -> FitGraph:
    r"""One ``RATIONAL_CUBIC`` node; ``cubic=False`` pins the $x^3$ coefficients at 0.

    NIST numbers these models b1..b5 (quadratic/quadratic) or b1..b7
    (cubic/cubic), numerator first. The kernel names them a0..a3 over b1..b3 with
    the denominator constant pinned at 1, which is how NIST writes them.
    """
    if cubic:
        num = [start["b1"], start["b2"], start["b3"], start["b4"]]
        den = [start["b5"], start["b6"], start["b7"]]
    else:
        num = [start["b1"], start["b2"], start["b3"], 0.0]
        den = [start["b4"], start["b5"], 0.0]
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="rat",
                model_type=ModelType.RATIONAL_CUBIC,
                parameters={
                    "a0": Parameter(value=num[0]),
                    "a1": Parameter(value=num[1]),
                    "a2": Parameter(value=num[2]),
                    "a3": Parameter(value=num[3], vary=cubic),
                    "b1": Parameter(value=den[0]),
                    "b2": Parameter(value=den[1]),
                    "b3": Parameter(value=den[2], vary=cubic),
                },
            ),
        ],
    )


def _project_rational_cubic(result: FitResult, *, cubic: bool) -> dict[str, float]:
    p = result.params
    out = {
        "b1": p["rat.a0"].value,
        "b2": p["rat.a1"].value,
        "b3": p["rat.a2"].value,
    }
    if cubic:
        out["b4"] = p["rat.a3"].value
        out["b5"] = p["rat.b1"].value
        out["b6"] = p["rat.b2"].value
        out["b7"] = p["rat.b3"].value
    else:
        out["b4"] = p["rat.b1"].value
        out["b5"] = p["rat.b2"].value
    return out


def _build_logistic_graph(start: dict[str, float], *, richards: bool) -> FitGraph:
    """One ``GENERALISED_LOGISTIC`` node; ``richards=False`` pins the exponent at 1.

    NIST's Rat42 is ``b1/(1 + exp(b2 - b3x))`` and Rat43 raises the denominator to
    ``1/b4``, so the plain logistic is the Richards curve with the shape exponent
    held at one rather than a separate model.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="log",
                model_type=ModelType.GENERALISED_LOGISTIC,
                parameters={
                    "amplitude": Parameter(value=start["b1"]),
                    "shift": Parameter(value=start["b2"]),
                    "rate": Parameter(value=start["b3"]),
                    "shape": Parameter(
                        value=start["b4"] if richards else 1.0,
                        vary=richards,
                    ),
                },
            ),
        ],
    )


def _project_logistic(result: FitResult, *, richards: bool) -> dict[str, float]:
    p = result.params
    out = {
        "b1": p["log.amplitude"].value,
        "b2": p["log.shift"].value,
        "b3": p["log.rate"].value,
    }
    if richards:
        out["b4"] = p["log.shape"].value
    return out


def _build_chwirut_graph(start: dict[str, float]) -> FitGraph:
    """One ``EXP_OVER_LINEAR`` node: ``exp(-b1x) / (b2 + b3x)``."""
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="eol",
                model_type=ModelType.EXP_OVER_LINEAR,
                parameters={
                    "rate": Parameter(value=start["b1"]),
                    "lin_const": Parameter(value=start["b2"]),
                    "lin_slope": Parameter(value=start["b3"]),
                },
            ),
        ],
    )


def _project_chwirut(result: FitResult) -> dict[str, float]:
    p = result.params
    return {
        "b1": p["eol.rate"].value,
        "b2": p["eol.lin_const"].value,
        "b3": p["eol.lin_slope"].value,
    }


_RECIPES: tuple[_NistRecipe, ...] = (
    _NistRecipe(
        name="Gauss1",
        model="b1·exp(-b2·x) + b3·exp(-(x-b4)²/b5²) + b6·exp(-(x-b7)²/b8²)",
        certified=gauss1.CERTIFIED,
        start=gauss1.START2,
        build=_build_two_gaussian_graph,
        project=_project_two_gaussian,
        x=gauss1.X.tolist(),
        y=gauss1.Y.tolist(),
    ),
    _NistRecipe(
        name="Gauss2",
        model="b1·exp(-b2·x) + b3·exp(-(x-b4)²/b5²) + b6·exp(-(x-b7)²/b8²)",
        certified=gauss2.CERTIFIED,
        start=gauss2.START2,
        build=_build_two_gaussian_graph,
        project=_project_two_gaussian,
        x=gauss2.X.tolist(),
        y=gauss2.Y.tolist(),
    ),
    _NistRecipe(
        name="Gauss3",
        model="b1·exp(-b2·x) + b3·exp(-(x-b4)²/b5²) + b6·exp(-(x-b7)²/b8²)",
        certified=gauss3.CERTIFIED,
        start=gauss3.START2,
        build=_build_two_gaussian_graph,
        project=_project_two_gaussian,
        x=gauss3.X.tolist(),
        y=gauss3.Y.tolist(),
    ),
    _NistRecipe(
        name="Lanczos1",
        model="b1·exp(-b2·x) + b3·exp(-b4·x) + b5·exp(-b6·x)",
        certified=lanczos1.CERTIFIED,
        start=lanczos1.START2,
        build=_build_lanczos_graph,
        project=_project_lanczos,
        x=lanczos1.X.tolist(),
        y=lanczos1.Y.tolist(),
    ),
    _NistRecipe(
        name="BoxBOD",
        model="b1·(1−exp(−b2·x))",
        certified=boxbod.CERTIFIED,
        start=boxbod.START2,
        build=_build_boxbod_graph,
        project=_project_boxbod,
        x=boxbod.X.tolist(),
        y=boxbod.Y.tolist(),
    ),
    _NistRecipe(
        name="Misra1a",
        model="b1·(1−exp(−b2·x))",
        certified=misra1a.CERTIFIED,
        start=misra1a.START2,
        build=_build_misra1a_graph,
        project=_project_misra1a,
        x=misra1a.X.tolist(),
        y=misra1a.Y.tolist(),
    ),
    _NistRecipe(
        name="Misra1b",
        model="b1·(1−(1+b2·x/2)^(−2))",
        certified=misra1b.CERTIFIED,
        start=misra1b.START2,
        build=_build_misra1b_graph,
        project=_project_misra1b,
        x=misra1b.X.tolist(),
        y=misra1b.Y.tolist(),
    ),
    _NistRecipe(
        name="MGH17",
        model="b1 + b2·exp(−b4·x) + b3·exp(−b5·x)",
        certified=mgh17.CERTIFIED,
        start=mgh17.START2,
        build=_build_mgh17_graph,
        project=_project_mgh17,
        x=mgh17.X.tolist(),
        y=mgh17.Y.tolist(),
    ),
    _NistRecipe(
        name="Bennett5",
        model="b1·(b2+x)^(−1/b3)",
        certified=bennett5.CERTIFIED,
        start=bennett5.START2,
        build=_build_bennett5_graph,
        project=_project_bennett5,
        x=bennett5.X.tolist(),
        y=bennett5.Y.tolist(),
    ),
    _NistRecipe(
        name="MGH09",
        model="b1·(x²+b2·x)/(x²+b3·x+b4)",
        certified=mgh09.CERTIFIED,
        start=mgh09.START2,
        build=_build_mgh09_graph,
        project=_project_mgh09,
        x=mgh09.X.tolist(),
        y=mgh09.Y.tolist(),
    ),
    _NistRecipe(
        name="Lanczos2",
        model="b1·exp(-b2·x) + b3·exp(-b4·x) + b5·exp(-b6·x)",
        certified=lanczos2.CERTIFIED,
        start=lanczos2.START2,
        build=_build_lanczos_graph,
        project=_project_lanczos,
        x=lanczos2.X.tolist(),
        y=lanczos2.Y.tolist(),
    ),
    _NistRecipe(
        name="Lanczos3",
        model="b1·exp(-b2·x) + b3·exp(-b4·x) + b5·exp(-b6·x)",
        certified=lanczos3.CERTIFIED,
        start=lanczos3.START2,
        build=_build_lanczos_graph,
        project=_project_lanczos,
        x=lanczos3.X.tolist(),
        y=lanczos3.Y.tolist(),
    ),
    _NistRecipe(
        name="Eckerle4",
        model="(b1/b2)·exp(-½·((x-b3)/b2)²)",
        certified=eckerle4.CERTIFIED,
        start=eckerle4.START2,
        build=_build_eckerle4_graph,
        project=_project_eckerle4,
        x=eckerle4.X.tolist(),
        y=eckerle4.Y.tolist(),
    ),
    _NistRecipe(
        name="Roszman1",
        model="b1 - b2·x - arctan(b3/(x-b4))/π",
        certified=roszman1.CERTIFIED,
        start=roszman1.START2,
        build=_build_roszman1_graph,
        project=_project_roszman1,
        x=roszman1.X.tolist(),
        y=roszman1.Y.tolist(),
    ),
    _NistRecipe(
        name="DanWood",
        model="b1·x^b2",
        certified=danwood.CERTIFIED,
        start=danwood.START2,
        build=_build_danwood_graph,
        project=_project_danwood,
        x=danwood.X.tolist(),
        y=danwood.Y.tolist(),
    ),
    _NistRecipe(
        name="Kirby2",
        model="(b1 + b2·x + b3·x²) / (1 + b4·x + b5·x²)",
        certified=kirby2.CERTIFIED,
        start=kirby2.START2,
        build=lambda s: _build_rational_cubic_graph(s, cubic=False),
        project=lambda r: _project_rational_cubic(r, cubic=False),
        x=kirby2.X.tolist(),
        y=kirby2.Y.tolist(),
    ),
    _NistRecipe(
        name="Hahn1",
        model="(b1 + b2·x + b3·x² + b4·x³) / (1 + b5·x + b6·x² + b7·x³)",
        certified=hahn1.CERTIFIED,
        start=hahn1.START2,
        build=lambda s: _build_rational_cubic_graph(s, cubic=True),
        project=lambda r: _project_rational_cubic(r, cubic=True),
        x=hahn1.X.tolist(),
        y=hahn1.Y.tolist(),
    ),
    _NistRecipe(
        name="Thurber",
        model="(b1 + b2·x + b3·x² + b4·x³) / (1 + b5·x + b6·x² + b7·x³)",
        certified=thurber.CERTIFIED,
        start=thurber.START2,
        build=lambda s: _build_rational_cubic_graph(s, cubic=True),
        project=lambda r: _project_rational_cubic(r, cubic=True),
        x=thurber.X.tolist(),
        y=thurber.Y.tolist(),
    ),
    _NistRecipe(
        name="Rat42",
        model="b1 / (1 + exp(b2 - b3·x))",
        certified=rat42.CERTIFIED,
        start=rat42.START2,
        build=lambda s: _build_logistic_graph(s, richards=False),
        project=lambda r: _project_logistic(r, richards=False),
        x=rat42.X.tolist(),
        y=rat42.Y.tolist(),
    ),
    _NistRecipe(
        name="Rat43",
        model="b1 / (1 + exp(b2 - b3·x))^(1/b4)",
        certified=rat43.CERTIFIED,
        start=rat43.START2,
        build=lambda s: _build_logistic_graph(s, richards=True),
        project=lambda r: _project_logistic(r, richards=True),
        x=rat43.X.tolist(),
        y=rat43.Y.tolist(),
    ),
    _NistRecipe(
        name="Chwirut1",
        model="exp(-b1·x) / (b2 + b3·x)",
        certified=chwirut1.CERTIFIED,
        start=chwirut1.START2,
        build=_build_chwirut_graph,
        project=_project_chwirut,
        x=chwirut1.X.tolist(),
        y=chwirut1.Y.tolist(),
    ),
    _NistRecipe(
        name="Chwirut2",
        model="exp(-b1·x) / (b2 + b3·x)",
        certified=chwirut2.CERTIFIED,
        start=chwirut2.START2,
        build=_build_chwirut_graph,
        project=_project_chwirut,
        x=chwirut2.X.tolist(),
        y=chwirut2.Y.tolist(),
    ),
)
r"""Info:
    Registry-over-map: declarative, one entry per StRD problem. START2 is used for
    every dataset (the robust guess the scenario RSS/$\chi^2$ assertions also fit from).
"""


def _validate_one(recipe: _NistRecipe, threshold: float) -> NistDataset:
    result = fit(
        recipe.build(recipe.start),
        MeasurementData(x=recipe.x, y=recipe.y),
        _LM_OPTS,
    )
    recovered = recipe.project(result)
    params = [
        NistParam(
            name=name,
            certified=certified_val,
            fitted=recovered[name],
            sig_figs_agreed=_sig_figs(recovered[name], certified_val),
        )
        for name, (certified_val, _stderr) in recipe.certified.items()
    ]
    min_sig = min(p.sig_figs_agreed for p in params)
    return NistDataset(
        name=recipe.name,
        model=recipe.model,
        n_params=len(params),
        params=params,
        min_sig_figs=min_sig,
        passed=min_sig >= threshold,
    )


def run_nist_validation(threshold: float = NIST_SIGFIG_THRESHOLD) -> NistValidation:
    r"""Fit the eight NIST StRD datasets and return their certified-value agreement.

    Each fit is tiny and deterministic; the whole sweep runs in ~0.3 s. Returns a
    :class:`NistValidation` whose ``passed`` is True iff every dataset recovers the
    NIST certified values to $\geq$ ``threshold`` significant figures.
    """
    datasets = [_validate_one(r, threshold) for r in _RECIPES]
    min_sig = min(d.min_sig_figs for d in datasets)
    return NistValidation(
        threshold_sig_figs=threshold,
        datasets=datasets,
        min_sig_figs=min_sig,
        passed=all(d.passed for d in datasets),
        total_available=NIST_STRD_TOTAL,
    )
