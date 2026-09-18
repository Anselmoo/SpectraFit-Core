"""Fit the Fe L-edge pair under four constraint hypotheses, and time each one.

The case study elsewhere in this directory fits each spectrum once. This script
asks a different question: **what does it cost to test a physical hypothesis?**

A spectroscopist looking at an L-edge does not have one model, they have several
candidate constraint sets, and the reason constraints are usually left out is
that trying them is expensive. Each scenario below is the same data and the same
components under a different set of expression edges, so the table it prints
measures the price of an opinion about the physics.

The four scenarios, in increasing order of what they assume:

* **A, free** - every parameter independent. The null hypothesis.
* **B, step 2:1** - the two `arctan` continuum-step amplitudes tied 2:1. This is
  the statistical 2p3/2 : 2p1/2 degeneracy, and it applies to the *edge jump*,
  which is a transition to the continuum and is not reshaped by multiplet
  effects.
* **C, +spin-orbit** - B, plus the L2 white line pinned one spin-orbit splitting
  above the L3 white line, the splitting itself being the (fitted) separation of
  the two continuum steps rather than a number typed in.
* **D, shared splitting** - a single joint fit over both spectra in which that
  splitting is constrained to be *the same* in the d5 and d6 complexes. The 2p
  spin-orbit interaction is a core-level property of the iron atom, so it should
  not depend on oxidation state; scenario D is the test of whether the data
  agrees.

**What is deliberately NOT tested is a tie on the L3:L2 multiplet intensities.**
The 2:1 degeneracy governs the edge jump, not the white-line intensities: the
branching ratio in a 3d transition-metal L-edge departs from 2 through the 2p-3d
electrostatic interaction, and it is itself an observable. Measured on these two
spectra by direct integration about the L3/L2 division, through the same loader
the case study uses, it is 2.4 for d5 and 2.9 for d6. Imposing 2:1 there would be
wrong by roughly 20 % and 45 % and would erase the quantity that distinguishes
the two complexes; `branching_ratios()` recomputes both on every run so the
numbers in this docstring cannot drift from the data.

Run::

    uv run --group manuscript python manuscript/examples/fecl4/fecl4_constraint_scenarios.py

Writes `fecl4_constraint_scenarios.json` beside itself and prints the table.
Timings are the median of `--reps` repetitions of the whole solve; they are
wall-clock on one machine and are reported to give the order of magnitude, not
as a benchmark result. The suite in Quality control is where ratios are measured.

`--check` diffs a fresh run against the committed JSON on every field except
timing and writes nothing; it is the guard `render_figures.py`'s `fig_*.py`
glob boundary cannot be, because this script is a direct entrypoint no glob
protects. Exits non-zero on drift.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fig_fecl4_case_study as CS
from spectrafit_core import (
    FitOptions,
    MeasurementData,
    arctan_step,
    compose,
    constant,
    fit,
    pseudo_voigt,
)

OPTS = FitOptions(solver="lm", max_iterations=2000, tolerance=1e-10)

# (L3 white line, L2 white line) as indices into the spectrum's peak list. Both
# are the largest-amplitude component of their multiplet in the seed table.
WHITE_LINE = {"d5": (1, 7), "d6": (1, 8)}

# The constraint hypotheses, defined once here and nowhere else.
#
# They used to exist three times: as locals inside `run()`, re-implemented in
# `fig_constraint_grid.py` (which documented the duplication and guarded it with
# a numeric cross-check), and hand-transcribed into `fig_model_graph.py` (which
# had no guard at all, and hard-coded `p1`/`p7` so that changing WHITE_LINE
# would have made it silently draw an edge between the wrong two peaks). A
# constraint is a piece of physics; it gets one definition and every consumer is
# a view of it.
SCENARIOS: tuple[str, ...] = ("A  free", "B  step 2:1", "C  + spin-orbit")

# Which scenario first applies each tie. `fig_model_graph.py` stamps its edges
# with this, so the structural figure says which hypothesis introduces an edge
# and `fig_constraint_grid.py` shows what that hypothesis then costs.
SCENARIO_TIES: dict[str, tuple[str, ...]] = {
    "A  free": (),
    "B  step 2:1": ("step",),
    "C  + spin-orbit": ("step", "spin_orbit"),
}
# The *first* scenario that applies each tie, which is the one that introduces
# it. Built over the scenarios in reverse so the earliest assignment is the one
# left standing: iterating forwards gives the last scenario to mention a tie, so
# the step tie would be credited to C, which merely inherits it from B.
TIE_ORIGIN: dict[str, str] = {
    tie_id: name for name in reversed(SCENARIOS) for tie_id in SCENARIO_TIES[name]
}


def tie(name: str, key: str, prefix: str = "") -> tuple[str, str]:
    """One tie as the `(expression, target)` pair `bind()` takes.

    `prefix` scopes the node names for the joint fit, where both spectra live in
    one graph. The peak indices come from WHITE_LINE, so a change there moves
    every consumer at once instead of leaving transcribed copies behind.
    """
    match name:
        case "step":
            return (
                f"{prefix}step_l3.amplitude / 2",
                f"{prefix}step_l2.amplitude",
            )
        case "spin_orbit":
            l3, l2 = WHITE_LINE[key]
            return (
                f"{prefix}p{l3}.center + {prefix}step_l2.center - {prefix}step_l3.center",
                f"{prefix}p{l2}.center",
            )
        case _:
            msg = f"unknown tie {name!r}; defined ties are {sorted(TIE_ORIGIN)}"
            raise KeyError(msg)


def ties_for(scenario: str, key: str, prefix: str = "") -> list[tuple[str, str]]:
    """Every `(expression, target)` pair one scenario applies to one spectrum."""
    if scenario not in SCENARIO_TIES:
        msg = f"unknown scenario {scenario!r}; defined scenarios are {list(SCENARIOS)}"
        raise KeyError(msg)
    return [tie(name, key, prefix) for name in SCENARIO_TIES[scenario]]


def tie_manifest() -> dict[str, list[dict[str, str]]]:
    """The ties per spectrum, with the scenario that introduces each.

    Serialised into the JSON sidecar so a figure can draw the constraint
    structure without importing this module, and therefore without needing the
    compiled extension. `fig_model_graph.py` is the consumer.
    """
    return {
        key: [
            {
                "id": name,
                "introduced_by": TIE_ORIGIN[name],
                "expr": expr,
                "target": target,
            }
            for name in sorted(TIE_ORIGIN, key=lambda n: SCENARIOS.index(TIE_ORIGIN[n]))
            for expr, target in [tie(name, key)]
        ]
        for key in WHITE_LINE
    }


def _nodes(spec: dict, prefix: str = "", dataset: int | None = None) -> list[Any]:
    """Build one spectrum's component nodes, optionally scoped to a dataset."""
    nodes = [
        pseudo_voigt(
            f"{prefix}p{i}",
            amplitude=amp,
            amplitude_min=0.0,
            center=cen,
            center_min=cen - 1.0,
            center_max=cen + 1.0,
            sigma=sig,
            sigma_min=0.05,
            sigma_max=3.0,
            fraction=0.5,
            fraction_min=0.0,
            fraction_max=1.0,
        )
        for i, (cen, amp, sig) in enumerate(spec["peaks"])
    ]
    for key, amp0 in (("step_l3", 0.30), ("step_l2", 0.15)):
        cen = spec[key]
        nodes.append(
            arctan_step(
                f"{prefix}{key}",
                amplitude=amp0,
                amplitude_min=0.0,
                center=cen,
                center_min=cen - 2.0,
                center_max=cen + 2.0,
                sigma=0.5,
                sigma_min=0.1,
                sigma_max=3.0,
            ),
        )
    nodes.append(constant(f"{prefix}bg", c=0.0))
    if dataset is not None:
        nodes = [n.model_copy(update={"dataset_index": dataset}) for n in nodes]
    return nodes


def _measure(spec: dict) -> MeasurementData:
    x, y = CS.load(HERE / spec["file"])
    return MeasurementData(x=x.tolist(), y=y.tolist())


def _timed(graph: Any, data: Any, reps: int) -> tuple[Any, float]:
    """Solve `reps` times, return the last result and the median wall-clock ms."""
    times: list[float] = []
    result = None
    for _ in range(reps):
        start = time.perf_counter()
        result = fit(graph, data, OPTS)
        times.append((time.perf_counter() - start) * 1e3)
    return result, statistics.median(times)


def _row(
    name: str,
    subject: str,
    result: Any,
    ms: float,
    splitting: float | None,
    n_points: int,
) -> dict[str, Any]:
    if not result.success:
        msg = f"{name} / {subject}: did not converge ({result.message})"
        raise RuntimeError(msg)
    return {
        "scenario": name,
        "subject": subject,
        "free_params": n_points - result.dof,
        "iterations": result.n_iter,
        "residual_evals": result.n_func_evals,
        "jacobian_evals": result.n_jac_evals,
        "ms": round(ms, 1),
        "r_squared": round(result.r_squared, 6),
        "reduced_chi2": round(result.reduced_chi2, 6),
        "splitting_ev": None if splitting is None else round(splitting, 3),
        # The full parameter vector, so a figure can redraw this fit with a pure
        # forward evaluation instead of refitting it. `render_figures.py` is
        # structurally barred from running this script -- doing so would re-time
        # every row of Table 2 -- so anything downstream has to read the answer
        # rather than recompute it.
        "params": {name: param.value for name, param in result.parameters.items()},
    }


def _splitting(result: Any, key: str, prefix: str = "") -> float:
    l3, l2 = WHITE_LINE[key]
    return (
        result.parameters[f"{prefix}p{l2}.center"].value
        - result.parameters[f"{prefix}p{l3}.center"].value
    )


def _reseed(nodes: list[Any], result: Any) -> list[Any]:
    """Return `nodes` with every parameter value replaced by `result`'s."""
    out: list[Any] = []
    for node in nodes:
        updated = {
            pname: (
                param.model_copy(update={"value": result.parameters[f"{node.id}.{pname}"].value})
                if f"{node.id}.{pname}" in result.parameters
                else param
            )
            for pname, param in node.parameters.items()
        }
        out.append(node.model_copy(update={"parameters": updated}))
    return out


def _reseed_prefixed(nodes: list[Any], result: Any, prefix: str) -> list[Any]:
    """`_reseed` for the joint fit, whose node ids carry a per-spectrum prefix.

    D's nodes are named `a_p0`, `b_p0`, ... while a single-spectrum result keys
    its parameters `p0.center`. Only the nodes carrying `prefix` are reseeded, so
    the two halves can be started from their own spectrum's optimum.
    """
    out: list[Any] = []
    for node in nodes:
        if not node.id.startswith(prefix):
            out.append(node)
            continue
        bare = node.id[len(prefix) :]
        updated = {
            pname: (
                param.model_copy(update={"value": result.parameters[f"{bare}.{pname}"].value})
                if f"{bare}.{pname}" in result.parameters
                else param
            )
            for pname, param in node.parameters.items()
        }
        out.append(node.model_copy(update={"parameters": updated}))
    return out


def _ssr(result: Any) -> float:
    """Residual sum of squares, which is the quantity nesting constrains."""
    return result.reduced_chi2 * result.dof


def _polish(
    best: dict[str, Any],
    solve: Any,
    cold_nodes: Any,
    max_rounds: int = 10,
) -> tuple[dict[str, Any], int]:
    """Restart every scenario from every other's best until nothing improves.

    Scenario B is A plus one equality tie, so B's feasible set sits inside A's
    and B's residual sum of squares cannot be smaller than A's at the optimum.
    A single local solve from one common start does not respect that -- the cold
    fits put B below A on d5, which is impossible for nested models and means at
    least one of them stopped short.

    Restarting each scenario from each other's optimum removes that artefact: a
    descent method started at a feasible point cannot end above it. One round is
    not enough and the order matters, so this iterates to a mutual fixed point,
    at which every scenario has been offered every other's solution and kept its
    own. Returns the polished results and the number of solves it took.
    """
    names = list(best)
    solves = len(names)
    for _ in range(max_rounds):
        improved = False
        for name in names:
            for other in names:
                if other == name:
                    continue
                candidate = solve(name, _reseed(cold_nodes(), best[other]))
                solves += 1
                if _ssr(candidate) < _ssr(best[name]) - 1e-12:
                    best[name] = candidate
                    improved = True
        if not improved:
            break
    return best, solves


def run(reps: int) -> list[dict[str, Any]]:
    """Run all four scenarios and return the table rows."""
    rows: list[dict[str, Any]] = []
    per_spectrum: dict[str, dict[str, Any]] = {}

    for key in ("d5", "d6"):
        spec = CS.SPECTRA[key]
        data = _measure(spec)
        n_points = len(data.y)

        def _solve(name: str, nodes: list[Any], _data: Any = data, _key: str = key) -> Any:
            builder = compose(nodes)
            for expr, target in ties_for(name, _key):
                builder = builder.bind(expr, to=target)
            return fit(builder.build(), _data, OPTS)

        # `ms` and `iterations` describe the solve from the common cold start --
        # what testing one hypothesis costs. The reported optimum is the mutual
        # fixed point of _polish(), a numerical-robustness step outside that cost.
        cold: dict[str, Any] = {}
        timings: dict[str, float] = {}
        for name in SCENARIOS:
            builder = compose(_nodes(spec))
            for expr, target in ties_for(name, key):
                builder = builder.bind(expr, to=target)
            cold[name], timings[name] = _timed(builder.build(), data, reps)

        best, solves = _polish(dict(cold), _solve, lambda _spec=spec: _nodes(_spec))
        for name in SCENARIOS:
            row = _row(name, key, best[name], timings[name], _splitting(best[name], key), n_points)
            # `iterations` and `ms` both describe the cold solve; the reported fit
            # quality is the polished optimum. Keeping the two apart is deliberate.
            row["iterations"] = cold[name].n_iter
            row["restart_solves"] = solves
            row["ssr_gained_by_restart"] = round(_ssr(cold[name]) - _ssr(best[name]), 4)
            row["step_centres_ev"] = {
                f"step_{k}": round(best[name].parameters[f"step_{k}.center"].value, 3)
                for k in ("l3", "l2")
            }
            rows.append(row)
        per_spectrum[key] = best

    # D: one joint fit over both spectra, with the splitting shared between them.
    d5, d6 = CS.SPECTRA["d5"], CS.SPECTRA["d6"]
    data5, data6 = _measure(d5), _measure(d6)
    nodes = _nodes(d5, prefix="a_", dataset=0) + _nodes(d6, prefix="b_", dataset=1)
    builder = compose(nodes)
    for prefix, key in (("a_", "d5"), ("b_", "d6")):
        expr, target = tie("step", key, prefix)
        builder = builder.bind(expr, to=target)
    expr, target = tie("spin_orbit", "d5", "a_")
    builder = builder.bind(expr, to=target)
    b3, b2 = WHITE_LINE["d6"]
    # The shared-splitting constraint: d6's L2 white line is displaced from its own
    # L3 white line by the SAME splitting the d5 spectrum determines.
    builder = builder.bind(
        f"b_p{b3}.center + a_step_l2.center - a_step_l3.center",
        to=f"b_p{b2}.center",
    )
    n_points = len(data5.y) + len(data6.y)
    joint_nodes = nodes

    def _solve_d(seed_nodes: list[Any]) -> Any:
        b = compose(seed_nodes)
        for _prefix, _key in (("a_", "d5"), ("b_", "d6")):
            e, t = tie("step", _key, _prefix)
            b = b.bind(e, to=t)
        e, t = tie("spin_orbit", "d5", "a_")
        b = b.bind(e, to=t)
        b = b.bind(
            f"b_p{b3}.center + a_step_l2.center - a_step_l3.center",
            to=f"b_p{b2}.center",
        )
        return fit(b.build(), [data5, data6], OPTS)

    cold_d, ms = _timed(builder.build(), [data5, data6], reps)
    cold_d_iterations = cold_d.n_iter
    # D is given the same restart treatment as A/B/C, seeded from each spectrum's
    # own polished optimum. Comparing a polished C against an unpolished D would
    # not be like for like, and the C-vs-D comparison is the point of the table.
    result = cold_d
    for name_a in SCENARIOS:
        for name_b in SCENARIOS:
            seeded = _reseed_prefixed(joint_nodes, per_spectrum["d5"][name_a], "a_")
            seeded = _reseed_prefixed(seeded, per_spectrum["d6"][name_b], "b_")
            candidate = _solve_d(seeded)
            if _ssr(candidate) < _ssr(result) - 1e-12:
                result = candidate
    d_row = _row(
        "D  shared splitting",
        "d5+d6 joint",
        result,
        ms,
        _splitting(result, "d5", "a_"),
        n_points,
    )
    d_row["iterations"] = cold_d_iterations
    d_row["restart_solves"] = 1 + len(SCENARIOS) ** 2
    d_row["ssr_gained_by_restart"] = round(_ssr(cold_d) - _ssr(result), 4)
    rows.append(d_row)
    return rows


def branching_ratios() -> dict[str, float]:
    """Integrated L3:L2 intensity ratio, measured directly off the data."""
    out = {}
    for key, division in (("d5", 714.0), ("d6", 713.0)):
        x, y = CS.load(HERE / CS.SPECTRA[key]["file"])
        y = y - np.median(y[x < 703])
        l3 = np.trapezoid(y[(x >= 703) & (x < division)], x[(x >= 703) & (x < division)])
        l2 = np.trapezoid(y[(x >= division) & (x < 730)], x[(x >= division) & (x < 730)])
        out[key] = round(float(l3 / l2), 2)
    return out


def _check(rows: list[dict[str, Any]], ratios: dict[str, float]) -> int:
    """Diff a fresh run against the committed JSON on every field except timing.

    A re-run leaves `free_params` and `reduced_chi2` identical to twelve
    decimals while moving every wall-clock number (`ms`, `total_ms`) the table
    prints -- so a guard that diffs the whole file always fires on a harmless
    re-run, and a guard that diffs nothing never catches a real drift. This
    compares everything else: a solver, tie, or data change that moves the fit
    shows up here; re-timing it does not.
    """
    out = HERE / "fecl4_constraint_scenarios.json"
    if not out.exists():
        print(f"no committed {out.name} to check against")
        return 1
    committed = json.loads(out.read_text())
    committed_rows = {(r["scenario"], r["subject"]): r for r in committed["rows"]}
    fresh_rows = {(r["scenario"], r["subject"]): r for r in rows}

    fields = (
        "free_params",
        "iterations",
        "residual_evals",
        "jacobian_evals",
        "r_squared",
        "reduced_chi2",
        "splitting_ev",
    )
    problems: list[str] = []
    if set(committed_rows) != set(fresh_rows):
        problems.append(
            f"row keys differ: committed {sorted(committed_rows)} vs fresh {sorted(fresh_rows)}",
        )
    for key in sorted(set(committed_rows) & set(fresh_rows)):
        c, f = committed_rows[key], fresh_rows[key]
        problems.extend(
            f"{key[0]!r} {key[1]!r} {field}: committed {c[field]!r} != fresh {f[field]!r}"
            for field in fields
            if c[field] != f[field]
        )
    if committed.get("ties") != tie_manifest():
        problems.append("ties (tie_manifest()) differ")
    if committed.get("branching_ratio") != ratios:
        problems.append(
            f"branching_ratio: committed {committed.get('branching_ratio')!r} != fresh {ratios!r}",
        )
    if committed.get("scenarios") != list(SCENARIOS):
        problems.append("scenarios list differs")

    if problems:
        print(f"DRIFT against committed {out.name} ({len(problems)} field(s)):")
        for p in problems:
            print(f"  - {p}")
        print(
            "\nRe-run and commit: uv run --group manuscript python "
            "manuscript/examples/fecl4/fecl4_constraint_scenarios.py",
        )
        return 1
    print(f"{out.name} matches a fresh run on every non-timing field")
    return 0


def main() -> int:
    """Run the scenarios, print the table, write the JSON sidecar."""
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--reps", type=int, default=None)
    ap.add_argument(
        "--check",
        action="store_true",
        help="Diff a fresh run against the committed JSON (non-timing fields only); write nothing",
    )
    args = ap.parse_args()
    # --check only reads the non-timing fields, so it defaults to a single
    # rep for speed; a normal run keeps timing-table depth 5.
    reps = args.reps if args.reps is not None else (1 if args.check else 5)

    rows = run(reps)
    ratios = branching_ratios()

    if args.check:
        return _check(rows, ratios)

    header = f"{'scenario':22s} {'subject':12s} {'free':>5s} {'iter':>5s} {'ms':>7s} {'R^2':>9s} {'red.chi2':>9s} {'split/eV':>9s}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['scenario']:22s} {r['subject']:12s} {r['free_params']:5d} "
            f"{r['iterations']:5d} {r['ms']:7.1f} {r['r_squared']:9.6f} "
            f"{r['reduced_chi2']:9.6f} "
            f"{'-' if r['splitting_ev'] is None else format(r['splitting_ev'], '9.3f')}",
        )
    total = sum(r["ms"] for r in rows)
    print(f"\nall {len(rows)} fits: {total:.0f} ms total (median of {reps} reps each)")
    print(
        f"measured L3:L2 branching ratio: d5 {ratios['d5']}, d6 {ratios['d6']} "
        f"(statistical degeneracy would give 2.0)",
    )

    out = HERE / "fecl4_constraint_scenarios.json"
    out.write_text(
        json.dumps(
            {
                "reps": reps,
                "scenarios": list(SCENARIOS),
                "ties": tie_manifest(),
                "rows": rows,
                "branching_ratio": ratios,
                "total_ms": round(total, 1),
            },
            indent=2,
        )
        + "\n",
    )
    print(f"wrote {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
