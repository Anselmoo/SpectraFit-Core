"""Figure: cross-backend performance profile over the benchmark suite.

Renders a Dolan-More performance profile from the sidecar written by
`extract_bench_summary.py`. For each case, every backend's median solve time is
divided by the fastest time any backend achieved on that case; the profile then
plots, for each backend, the fraction of cases solved within a factor tau of the
best. A curve's intercept at tau = 1 is how often that backend was outright
fastest; its right-hand asymptote is the fraction of cases it solved at all.

Reproduce:

    uv run --group manuscript python manuscript/examples/figures/extract_bench_summary.py <run-dir>
    uv run --group manuscript python manuscript/examples/figures/fig_benchmark_profile.py

Outputs, written next to this file:
    fig_benchmark_profile.pdf   vector, for submission
    fig_benchmark_profile.png   300 dpi raster

Why a performance profile rather than a bar chart of mean speedups: a mean over
cases is dominated by whichever case happens to be slowest in absolute terms,
and hides how often a backend is merely *close* to the best rather than far
behind. The profile answers "how often is this backend within 2x of the best?"
directly, which is the question a reader choosing a solver actually has.

A backend that never RAN is excluded from the plot and named in the subtitle.
An earlier version drew it as a flat zero, which is a different and false
claim: "attempted 151 cases and solved none" rather than "was not exercised".
This run installs the `benchmark` extra but not the optional `jax` extra, so
JAX/optimistix produced no per-case results at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import numpy as np
from matplotlib import pyplot as plt

HERE = Path(__file__).resolve().parent
SUMMARY = HERE / "bench_summary.json"

# Chart series ramp from docs/stylesheets/tokens/palette.css (--c-chart-1..5).
#
# One hue per backend, so the scipy configurations can be compared with each
# other and not only against the subject. That was not free. The raw brand
# `--c-<backend>` colours cannot do it: measured all-pairs, systemIndigo vs
# systemBlue is dE 0.8 under deuteranopia and 7.0 with normal vision, because
# deuteranopia merges red/green/orange into one family and blue/indigo/cyan
# into another. Extending the previous four-hue chart ramp to five also failed
# outright — five separate candidate fifth hues each broke the normal-vision
# floor — so the set was re-derived as a whole, with slot 3 lightened.
#
# Measured (--pairs all, light surface): lightness PASS, chroma PASS,
# normal-vision PASS at dE 16.5 (threshold 15), CVD separation WARN at 7.0
# deutan (inside the 6-8 floor band), contrast WARN for chart-5 at 2.82.
#
# Both WARNs are legal ONLY with secondary encoding, which is why every series
# also carries a distinct dash pattern and is named with its solved-count in
# the legend. Five is the measured ceiling: a sixth hue has nowhere to go that
# does not collapse a pair, and the honest remedy there is faceting.
SERIES_COLOUR = {
    "spectrafit": "#0067d6",  # --c-chart-1
    "lmfit": "#9c5f00",  # --c-chart-2  (the timing baseline)
    "scipy-ls-lm": "#00875f",  # --c-chart-3
    "scipy-ls-trf": "#b03a8f",  # --c-chart-4
    "scipy-ls-dogbox": "#4a9fd8",  # --c-chart-5  (the sub-3:1 slot)
}
# Dash patterns are retained even though every series now has its own hue:
# the CVD and contrast WARNs above are legal only WITH secondary encoding, and
# this is it. They also keep the chart readable in greyscale print.
DASHES = {
    "spectrafit": (None, None),
    "lmfit": (6, 2),
    "scipy-ls-lm": (1, 2),
    "scipy-ls-trf": (9, 2, 1, 2),
    "scipy-ls-dogbox": (3, 3),
}
# A backend offered fewer than this fraction of the suite is excluded from the
# profile rather than drawn with a structurally-capped curve. 0.9 keeps the
# scipy configurations (offered 147 of 151) and drops jax/optimistix (58).
ELIGIBILITY_FLOOR = 0.9

C_SUBJECT = SERIES_COLOUR["spectrafit"]
C_FALLBACK = "#8e8e93"
INK = "#1d1d1f"
INK_MUTED = "#6e6e73"
GRID = "#e3e3e0"

# The subject of the benchmark always takes slot 0 (the strongest hue, solid
# line); oracles follow in a fixed order so a backend's colour never changes
# between figures or runs.
PREFERRED_ORDER = [
    "spectrafit",
    "lmfit",
    "jax",
    "scipy-ls-lm",
    "scipy-ls-trf",
    "scipy-ls-dogbox",
]


def load_summary() -> dict:
    """Load the sidecar, failing with the command that produces it."""
    if not SUMMARY.exists():
        msg = (
            f"{SUMMARY} not found — run extract_bench_summary.py against a "
            "benchmark run directory first"
        )
        raise SystemExit(msg)
    return json.loads(SUMMARY.read_text())


def performance_ratios(summary: dict) -> tuple[list[str], dict[str, np.ndarray], dict]:
    """Return (ordered solvers, per-solver ratio arrays, coverage stats).

    A case contributes a ratio for a backend only when that backend succeeded on
    it. Failures become ``inf`` so they never count as "solved within tau" at
    any finite tau, which is exactly how Dolan-More handles them.
    """
    # A performance profile is only meaningful over a case set every plotted
    # backend was actually offered. Two distinct things had been conflated:
    #
    #   eligible  — the backend was asked to run the case (it has an entry)
    #   succeeded — it was asked, and converged
    #
    # Reporting "solved / total cases" mixes them. In the canonical run
    # scipy-ls-lm shows 146 successes against 151 cases, which reads as five
    # failures; it was offered 147 and failed one. trf and dogbox were offered
    # 147 and failed none, not four. And jax/optimistix is offered 58 of 151,
    # because optimistix cannot express the expression edges the tied-parameter
    # cases use — a curve flattening at 0.38 would read as mass failure when it
    # was never asked to attempt those cases at all.
    #
    # So: drop backends whose eligibility is structurally low (they are named in
    # the subtitle and discussed in the text), then restrict to the cases every
    # remaining backend was offered, and report counts against THAT set.
    eligible = summary.get("solvers_eligible")
    if eligible is None:  # sidecar predates the eligibility split
        eligible = dict.fromkeys(summary["solvers"], len(summary["cases"]))
    n_total = len(summary["cases"])
    plotted = {s for s in summary["solvers"] if eligible.get(s, 0) >= ELIGIBILITY_FLOOR * n_total}

    solvers = [s for s in PREFERRED_ORDER if s in plotted]
    solvers += [s for s in summary["solvers"] if s in plotted and s not in solvers]

    common = [c for c in summary["cases"] if all(s in c["m"] for s in solvers)]

    ratios: dict[str, list[float]] = {s: [] for s in solvers}
    solved: dict[str, int] = dict.fromkeys(solvers, 0)

    for case in common:
        times = {}
        for s in solvers:
            m = case["m"].get(s)
            if m and m.get("success") and m.get("med_ms"):
                times[s] = float(m["med_ms"])
        if not times:
            continue
        best = min(times.values())
        for s in solvers:
            if s in times:
                ratios[s].append(times[s] / best)
                solved[s] += 1
            else:
                ratios[s].append(np.inf)

    coverage = {s: (solved[s], len(common)) for s in solvers}
    return solvers, {s: np.asarray(v, dtype=float) for s, v in ratios.items()}, coverage


def plot(summary: dict) -> None:
    """Render the profile to PDF and 300 dpi PNG."""
    solvers, ratios, coverage = performance_ratios(summary)

    mpl.rcParams.update(
        {
            "font.size": 8,
            "axes.labelsize": 8,
            "legend.fontsize": 7,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "axes.edgecolor": INK_MUTED,
            "axes.linewidth": 0.6,
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "text.color": INK,
            "axes.labelcolor": INK,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        },
    )
    fig, ax = plt.subplots(figsize=(6.6, 4.2))

    finite = np.concatenate([r[np.isfinite(r)] for r in ratios.values() if r.size])
    tau_max = float(np.percentile(finite, 99.5)) if finite.size else 10.0
    tau = np.logspace(0, np.log10(max(tau_max, 2.0)), 400)

    handles = []
    for s in solvers:
        r = ratios[s]
        rho = [(r <= t).sum() / len(r) for t in tau] if r.size else np.zeros_like(tau)
        # One hue per backend. Weight still separates roles: the subject is
        # heaviest, the timing baseline next, the rest uniform — so the chart
        # reads as "spectrafit vs the baseline" at a glance while still
        # supporting a scipy-to-scipy comparison on closer reading.
        colour = SERIES_COLOUR.get(s, C_FALLBACK)
        if s == "spectrafit":
            lw = 1.9
        elif s == summary.get("baseline_solver_id", "lmfit"):
            lw = 1.5
        else:
            lw = 1.2
        dash = DASHES.get(s, (2, 2))
        (line,) = ax.plot(
            tau,
            rho,
            lw=lw,
            color=colour,
            dashes=dash if dash[0] is not None else (None, None),
            solid_capstyle="round",
        )
        solved, total = coverage[s]
        handles.append((line, f"{s}  ({solved}/{total} solved)"))

        # No right-edge direct labels: the legend below already names every
        # series AND carries its solved-count, which is the more useful number.
        # Two lookup mechanisms for the same fact is one too many, and the
        # labels collided where the grey curves converge.

    ax.set_xscale("log", base=2)
    ax.set_xlim(1, tau[-1])
    ax.set_ylim(0, 1.02)
    ax.set_xlabel(r"$\tau$  —  factor from the fastest backend on the same case")
    ax.set_ylabel(r"fraction of cases solved within $\tau$")
    ax.grid(True, color=GRID, lw=0.5)
    ax.set_axisbelow(True)

    # tau = 1 and the right-hand asymptote are the two canonical readings of a
    # performance profile — efficiency (how often fastest) and robustness (how
    # much it solved at all). Marked explicitly so a reader can take the
    # headline numbers off the chart instead of eyeballing the curve.
    subject = "spectrafit"
    if subject in ratios:
        r = ratios[subject]
        eff = float((r <= 1.0).sum() / len(r))
        solved_frac = coverage[subject][0] / coverage[subject][1]
        ax.axvline(1.0, color=INK_MUTED, lw=0.7, ls=(0, (1, 2)), zorder=1)
        ax.annotate(
            f"{subject}: {eff:.0%} fastest outright, {solved_frac:.0%} solved",
            xy=(1.0, eff),
            xytext=(10, -16),
            textcoords="offset points",
            fontsize=6.8,
            color=C_SUBJECT,
            arrowprops={"arrowstyle": "-", "lw": 0.6, "color": C_SUBJECT},
        )

    # A curve that plateaus below 1.0 has not run off the right edge — it never
    # solved those cases at all. Readers new to performance profiles routinely
    # misread this, and it is the difference between "slow" and "failed".
    ax.annotate(
        "a curve plateauing below 1.0 means unsolved cases, not a longer tail",
        xy=(0.5, -0.235),
        xycoords="axes fraction",
        ha="center",
        fontsize=6.5,
        color=INK_MUTED,
    )

    m = summary.get("manifest", {})
    n_common = coverage[solvers[0]][1] if solvers else 0
    # Two lines: one subtitle ran past the right edge and truncated the run id.
    subtitle = (
        f"{n_common} of {summary['n_cases']} cases, those offered to all "
        f"{len(solvers)} backends · baseline "
        f"{summary.get('baseline_solver_id', 'lmfit')} · run {m.get('run_id', '?')}"
    )
    second = ""
    elig = summary.get("solvers_eligible", {})
    dropped = [s for s in summary["solvers"] if s not in solvers]
    if dropped:
        detail = ", ".join(f"{s} (offered {elig.get(s, 0)}/{summary['n_cases']})" for s in dropped)
        second = f"excluded from the profile, partial coverage: {detail} — see text"
    ax.set_title(
        subtitle + ("\n" + second if second else ""),
        fontsize=7.2,
        color=INK_MUTED,
        loc="left",
        pad=8,
    )

    fig.legend(
        [h for h, _ in handles],
        [lab for _, lab in handles],
        loc="lower center",
        frameon=False,
        ncol=3,
        columnspacing=1.6,
        handlelength=2.6,
        bbox_to_anchor=(0.5, 0.0),
    )
    fig.subplots_adjust(left=0.085, right=0.98, top=0.89, bottom=0.30)
    for ext, dpi in (("pdf", None), ("png", 300)):
        fig.savefig(HERE / f"fig_benchmark_profile.{ext}", dpi=dpi)
    plt.close(fig)

    print("wrote fig_benchmark_profile.pdf / .png")
    for s in solvers:
        solved, total = coverage[s]
        note = "  <- solved nothing; disclosed as a flat zero" if solved == 0 else ""
        print(f"  {s:20s} {solved:4d}/{total} solved{note}")


if __name__ == "__main__":
    plot(load_summary())
