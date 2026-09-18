"""Appendix figure: cross-backend Dolan-More performance profile.

The figure exists to support one sentence — read in the conventional
performance-profile form, spectrafit-core is outright fastest on 86 % of the
cases every plotted backend was offered, it solved all of them, and where it is
not fastest it is close rather than far behind.

This is the standard-form companion to Figure 4. It is drawn from the same
sidecar, the same run and the same per-case median times; it exists so the
headline timing claim can be cross-checked in the presentation a reader of the
optimisation literature already knows how to read, rather than only in the
per-case form Figure 4 uses. If the two disagree, one of them is wrong; they are
kept side by side precisely so that check is available.

For each case, every backend's median solve time is divided by the fastest time
any backend achieved on that case; the profile then plots, for each backend, the
fraction of cases solved within a factor tau of the best. A curve's intercept at
tau = 1 is how often that backend was outright fastest; its right-hand asymptote
is the fraction of cases it solved at all. Both readings are written into the
legend so neither has to be eyeballed off the curve.

Reproduce:

    uv run --group manuscript python manuscript/examples/figures/extract_bench_summary.py <run-dir>
    uv run --group manuscript python manuscript/examples/figures/fig_performance_profile.py

Outputs, written next to this file:
    fig_performance_profile.pdf   vector, for submission
    fig_performance_profile.png   300 dpi raster

Why this presentation is the appendix and not the main figure
-------------------------------------------------------------
A performance profile requires one case set that every plotted curve was
offered, and this suite is ragged by design: the 4 tied-parameter cases are not
handed to SciPy, and those 4 plus the 20 multimodal `optfn` cases are not handed
to jax/optimistix. So the denominator is chosen by which subsets happen to
overlap, not by anything about the library. Intersecting five backends gives 147
of 151 cases. Intersecting all six gives 127.

The second number is the disqualifying one. On those 127 cases spectrafit-core
is fastest 100 % of the time — because the 20 cases it loses across the
147-case set are precisely the 20 multimodal `optfn` cases jax is never offered.
The single arrangement in which every backend shares a denominator is therefore
also the arrangement that deletes the subject's only measured weakness, moving
its score from 86 % to 100 % by discarding the evidence against it. A figure
whose denominator flatters the subject cannot be the figure that carries the
claim, so Figure 4 scores each backend over the cases it was actually offered
and keeps all 151, and this profile — drawn on the 147-case five-backend
intersection, with the excluded backend named and counted on the canvas — is
the appendix cross-check.

Why a profile rather than a bar chart of mean speedups: a mean over cases is
dominated by whichever case happens to be slowest in absolute terms, and hides
how often a backend is merely *close* to the best rather than far behind. The
profile answers "how often is this backend within 2x of the best?" directly,
which is the question a reader choosing a solver actually has.

A backend offered less than `ELIGIBILITY_FLOOR` of the suite is excluded from
the plot and named, with its offered-count, in the subtitle. The exclusion is
mechanical, not editorial. In this run it drops jax/optimistix, which ran and
converged on every case it was given but was given only 127 of 151: it is not
handed the 4 tied-parameter cases, whose expression edges optimistix cannot
express, nor the 20 multimodal `optfn` cases, which sit outside the local-fit
contract it is given.

Rejected alternatives, each recorded with what decided it
---------------------------------------------------------
An earlier version drew the excluded backend as a flat zero, which is a
different and false claim: "attempted 151 cases and solved none" rather than
"was not asked to attempt 24 of them". A later version stated the exclusion
correctly but gave it the wrong reason — that this run installed the `benchmark`
extra without the optional `jax` extra, so no per-case jax results existed. The
sidecar refutes that: `solvers_not_run` is empty and jax carries 127 successes.

A third version, in `performance_ratios`, fell back to
`dict.fromkeys(summary["solvers"], len(summary["cases"]))` when the sidecar
carried no `solvers_eligible` block. That fallback asserts "every backend was
offered every case", which is exactly the claim the flat-zero curve made, merely
inverted: it would readmit jax/optimistix as a curve structurally capped at
127/151 = 0.84 and read as mass failure. A missing eligibility block is now a
`SystemExit`, because drawing less is the only honest degradation and here there
is nothing left to draw.

Right-edge direct labels were drawn once and removed: the legend already names
every series and now carries both canonical readings, two lookup mechanisms for
one fact is one too many, and the labels collided where the four comparator
curves converge on 1.0. They are not to be re-added.

The tau axis is not cropped. An earlier version stopped it at the pooled 99.5th
percentile of the ratios; that hid 4 of 734 points off the right edge and left
lmfit's curve ending at 0.986 and scipy-ls-lm's at 0.980 while their legend
entries read 147/147 and 146/147 solved — precisely the misreading the caveat
under the axis warns against, manufactured by the crop rather than present in
the data. On a log-2 axis the entire hidden tail costs 17 % of the width, which
buys far too little legibility to be worth contradicting the figure's own
caveat.

The run id is not printed on the canvas. It names a directory rather than a
quantity, no reader can act on it, and the gold-standard figure
(`fig_ladder_stability.py`) prints none. Provenance for this figure lives in the
manuscript caption and in `manuscript/draft/manuscript-state.json`; what does
belong on the canvas is the timing depth, which is a measurement parameter, and
that is derived from the ladder rather than typed in.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import numpy as np
from matplotlib import pyplot as plt

# The rendered PNG is sha256-pinned in manuscript/draft/.render-manifest.json, so
# the backend is pinned too: an interactive backend resolves fonts differently
# and moves the hash without moving a single number.
mpl.use("Agg")

HERE = Path(__file__).resolve().parent
SUMMARY = HERE / "bench_summary.json"
LADDER = HERE.parent / "ladder" / "ladder.json"
RUNGS = HERE.parent / "ladder" / "rungs"
STEM = "fig_performance_profile"

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
# also carries a distinct dash pattern and is named with its counts in the
# legend. Five is the measured ceiling: a sixth hue has nowhere to go that
# does not collapse a pair, and the honest remedy there is faceting.
#
# Harmonised with Figure 4 (fig_benchmark_profile.py), and that is the whole of
# the colour rule here. This figure and that one plot the same backends on the
# same run, so a backend that changed hue between them would be the worst kind
# of collision the paper can contain: not two figures reusing a hue for
# different things, but one framework wearing two identities a page apart.
# Every assignment below is therefore a deliberate positive reuse — same
# referent, same hue, checked against Figure 4's SERIES_COLOUR.
#
# The subject sits OUTSIDE the chart ramp on #c1185b, the paper's subject
# crimson (fig_ladder_stability.py:174, fig_nist_head_to_head.py:41), so both
# figures read as subject-against-field rather than one-of-five. An earlier
# version of this file put the subject on #0067d6 and argued that "slot 1 is the
# subject's slot in every chart in the paper". That was never true of the
# palette and is now plainly false of Figure 4; the claim is recorded here as
# withdrawn rather than silently deleted.
#
# Retiring #0067d6 from this figure also retires its sharpest collision. That
# hex is lmfit — the COMPARATOR — at fig_nist_head_to_head.py:42, and in Figure 4
# it is jax. It is now absent here, so nothing in this figure inverts it.
#
# Declining-comment (R11d) for the four ramp hues that remain:
#   #9c5f00  is the arctan continuum step in Figures 1 and 3, and Figure 6's
#            "Average" tier. Declined: there is no continuum in a timing
#            profile. Reused from Figure 4, where it is also lmfit.
#   #00875f  is the L2 multiplet in Figure 3. Declined: no spectral feature is
#            plotted. Reused from Figure 4, where it is also scipy-ls-lm.
#   #b03a8f  is the total model in Figure 3 and Figure 6's "Higher" tier.
#            Declined: nothing here is a sum of components. Reused from Figure
#            4, where it is also scipy-ls-trf.
#   #4a9fd8  means scipy-ls-dogbox here and in Figure 4 and nothing anywhere
#            else; no meaning to decline.
#
# #d30f45, the reserved attention channel ("look here", R12), is declined
# outright: this figure has five co-equal curves and no single element it wants
# read first, so there is nothing for the attention hue to point at. Emphasis is
# carried by line weight instead (the subject is heaviest, the timing baseline
# next), the way fig_ladder_stability.py declines it for the same reason.
SERIES_COLOUR = {
    "spectrafit": "#c1185b",  # subject crimson, outside the ramp
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
# scipy configurations (offered 147 of 151, i.e. 0.97) and drops jax/optimistix
# (offered 127 of 151, i.e. 0.84). The floor sits between those two measured
# values and nowhere near either, so it is a rule and not a hand-picked cut.
ELIGIBILITY_FLOOR = 0.9

# A profile of one curve compares nothing, so two eligible backends is the
# structural minimum below which the figure refuses to draw.
MIN_PLOTTED_SOLVERS = 2

C_SUBJECT = SERIES_COLOUR["spectrafit"]
C_FALLBACK = "#8e8e93"
INK = "#1d1d1f"
INK_MUTED = "#6e6e73"
GRID = "#e3e3e0"

# Declared layer ranking (R6), stated once here rather than as inline ternaries
# at the call sites. Reading order bottom to top: the grid is scenery, the
# comparators are the field, the subject rides over them, labels ride over
# everything.
#
# Z_GRID is inert — `ax.set_axisbelow(True)` forces the grid under every artist
# regardless of its zorder — and is kept only so the full ranking is written
# down in one place rather than half here and half in an axes property.
Z_GRID = 0
Z_COMPARATOR = 2
Z_SUBJECT = 3
Z_ANNOTATION = 6

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

SUBJECT = "spectrafit"


def load_summary() -> dict:
    """Load the sidecar, failing with the command that produces it."""
    if not SUMMARY.exists():
        msg = (
            f"{SUMMARY} not found — the profile is drawn entirely from the "
            "per-case median times in the sidecar and there is nothing to plot "
            "without it; run extract_bench_summary.py against a benchmark run "
            "directory first"
        )
        raise SystemExit(msg)
    return json.loads(SUMMARY.read_text())


def timing_depth(run_id: str) -> tuple[int, int] | None:
    """Return (reps_requested, reps_effective) for the run, or ``None``.

    The sidecar records which run it came from but not how deeply that run was
    timed; the repetition ladder records the depth but indexes it by rung. The
    two are joined through the per-rung manifests, whose ``run_id`` matches the
    sidecar's and whose directory is named for ``reps_effective``.

    Returns ``None`` when the ladder or the manifests are unavailable, or when
    no rung claims this run, so the figure omits the depth line rather than
    inventing a number for it (R13).
    """
    if not LADDER.exists() or not RUNGS.is_dir():
        return None
    try:
        rungs = json.loads(LADDER.read_text()).get("rungs", [])
    except (OSError, json.JSONDecodeError):
        return None

    effective: int | None = None
    for manifest in sorted(RUNGS.glob("*/manifest.json")):
        try:
            if json.loads(manifest.read_text()).get("run_id") != run_id:
                continue
        except (OSError, json.JSONDecodeError):
            continue
        # The rung directory is named for its effective depth (rung_050 -> 50),
        # which is the key ladder.json indexes its rungs by.
        suffix = manifest.parent.name.rsplit("_", 1)[-1]
        if suffix.isdigit():
            effective = int(suffix)
        break

    if effective is None:
        return None
    for rung in rungs:
        if rung.get("reps_effective") == effective:
            return int(rung["reps_requested"]), effective
    return None


def performance_ratios(
    summary: dict,
) -> tuple[list[str], dict[str, np.ndarray], dict, int, dict[str, int]]:
    """Return (ordered solvers, ratio arrays, coverage, dropped, eligibility).

    A case contributes a ratio for a backend only when that backend succeeded on
    it. Failures become ``inf`` so they never count as "solved within tau" at
    any finite tau, which is exactly how Dolan-More handles them.

    ``dropped`` counts cases in which no plotted backend succeeded. Such a case
    has no best time, so it cannot enter a ratio at all; it is removed from the
    denominator and its count returned so the caller can disclose it on the
    canvas rather than let two denominators drift apart silently.

    The resolved eligibility mapping is returned rather than re-read by the
    caller: the exclusion decision and the offered-count printed next to the
    excluded backend must be the same object, or a sidecar shape this function
    tolerated could still print "offered 0/151" on the canvas.
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
    # 147 and failed none, not four. And jax/optimistix is offered 127 of 151 —
    # it is not handed the 4 tied-parameter cases, whose expression edges
    # optimistix cannot express, nor the 20 multimodal `optfn` cases — so a curve
    # flattening at 0.84 would read as mass failure when it was never asked to
    # attempt those 24 cases at all.
    #
    # So: drop backends whose eligibility is structurally low (they are named in
    # the subtitle and discussed in the text), then restrict to the cases every
    # remaining backend was offered, and report counts against THAT set.
    eligible = summary.get("solvers_eligible")
    if eligible is None:
        # Assuming full eligibility is not a weaker figure, it is a false one:
        # it readmits the partial backend as a curve structurally capped at its
        # offered fraction, which reads as mass failure. See the docstring.
        msg = (
            f"{SUMMARY} carries no `solvers_eligible` block — without it a "
            "partially-offered backend cannot be told from a failing one, and "
            "the profile would draw a curve capped at 0.84 that reads as mass "
            "failure; re-run extract_bench_summary.py against the run directory "
            "to write the eligibility block"
        )
        raise SystemExit(msg)

    n_total = len(summary["cases"])
    plotted = {s for s in summary["solvers"] if eligible.get(s, 0) >= ELIGIBILITY_FLOOR * n_total}

    solvers = [s for s in PREFERRED_ORDER if s in plotted]
    solvers += [s for s in summary["solvers"] if s in plotted and s not in solvers]

    if len(solvers) < MIN_PLOTTED_SOLVERS:
        msg = (
            f"only {len(solvers)} backend(s) clear the {ELIGIBILITY_FLOOR:.0%} "
            f"eligibility floor over {n_total} cases — a performance profile of "
            "one curve compares nothing, since every ratio would be 1.0 by "
            "construction; re-run the benchmark with at least two backends "
            "offered the whole suite"
        )
        raise SystemExit(msg)

    common = [c for c in summary["cases"] if all(s in c["m"] for s in solvers)]
    if not common:
        msg = (
            f"no case in {SUMMARY} was offered to all {len(solvers)} eligible "
            "backends, so no case has a per-case best time to divide by and the "
            "profile has an empty denominator; re-run the benchmark so the "
            "plotted backends share a case set"
        )
        raise SystemExit(msg)

    ratios: dict[str, list[float]] = {s: [] for s in solvers}
    solved: dict[str, int] = dict.fromkeys(solvers, 0)
    dropped = 0

    for case in common:
        times = {}
        for s in solvers:
            m = case["m"].get(s)
            if m and m.get("success") and m.get("med_ms"):
                times[s] = float(m["med_ms"])
        if not times:
            dropped += 1
            continue
        best = min(times.values())
        for s in solvers:
            if s in times:
                ratios[s].append(times[s] / best)
                solved[s] += 1
            else:
                ratios[s].append(np.inf)

    # The denominator is the number of cases that entered a ratio, not the number
    # offered, so the legend's solved-fraction and the curve's own right-hand
    # asymptote are the same quantity read two ways.
    n_used = len(common) - dropped
    coverage = {s: (solved[s], n_used) for s in solvers}
    arrays = {s: np.asarray(v, dtype=float) for s, v in ratios.items()}
    return solvers, arrays, coverage, dropped, eligible


def plot(summary: dict) -> None:
    """Render the profile to PDF and 300 dpi PNG."""
    solvers, ratios, coverage, dropped, eligible = performance_ratios(summary)

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
    fig, ax = plt.subplots(figsize=(6.6, 4.6))

    finite = np.concatenate([r[np.isfinite(r)] for r in ratios.values() if r.size])
    tau_max = float(finite.max()) if finite.size else 10.0
    tau = np.logspace(0, np.log10(max(tau_max, 2.0)), 400)

    baseline = summary.get("baseline_solver_id", "lmfit")
    handles = []
    efficiency: dict[str, float] = {}
    for s in solvers:
        r = ratios[s]
        rho = [(r <= t).sum() / len(r) for t in tau] if r.size else np.zeros_like(tau)
        # One hue per backend. Weight still separates roles: the subject is
        # heaviest, the timing baseline next, the rest uniform — so the chart
        # reads as "spectrafit vs the baseline" at a glance while still
        # supporting a scipy-to-scipy comparison on closer reading.
        colour = SERIES_COLOUR.get(s, C_FALLBACK)
        if s == SUBJECT:
            lw = 1.9
        elif s == baseline:
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
            zorder=Z_SUBJECT if s == SUBJECT else Z_COMPARATOR,
        )
        solved, total = coverage[s]
        fastest = int((r <= 1.0).sum()) if r.size else 0
        efficiency[s] = fastest / len(r) if r.size else 0.0
        # Both canonical readings of a performance profile, in the key, against
        # one shared denominator: the intercept at tau = 1 (how often fastest)
        # and the right-hand asymptote (how much it solved at all). Writing only
        # the second left the first to be eyeballed off a curve whose four
        # comparator traces start within a few pixels of each other.
        handles.append((line, f"{s}   fastest {fastest}/{total} · solved {solved}/{total}"))

        # No right-edge direct labels: the legend below already names every
        # series AND carries both readings, which is the more useful pair of
        # numbers. Two lookup mechanisms for the same fact is one too many, and
        # the labels collided where the four comparator curves converge on 1.0.

    ax.set_xscale("log", base=2)
    ax.set_xlim(1, tau[-1])
    ax.set_ylim(0, 1.02)
    ax.set_xlabel(r"$\tau$ (factor from the fastest backend on the same case)")
    ax.set_ylabel(r"fraction of cases solved within $\tau$")
    ax.grid(True, color=GRID, lw=0.5, zorder=Z_GRID)
    ax.set_axisbelow(True)

    # The legend carries both readings as counts; this one annotation attaches
    # the subject's pair to the geometry they are read off, so a reader learns
    # where on the curve those numbers live rather than taking them on trust.
    #
    # A dotted rule used to be drawn at tau = 1 to mark the first of the two
    # readings. It rendered as nothing: the axis starts at tau = 1 (a ratio
    # below 1 is impossible by construction), so the rule fell exactly under the
    # left spine at every figure size. The spine IS the tau = 1 rule, the 2^0
    # tick names it, and the annotation reads the intercept off it.
    if SUBJECT in ratios:
        solved, total = coverage[SUBJECT]
        ax.annotate(
            f"{SUBJECT}: {efficiency[SUBJECT]:.0%} fastest outright, {solved / total:.0%} solved",
            xy=(1.0, efficiency[SUBJECT]),
            xytext=(10, -16),
            textcoords="offset points",
            fontsize=6.8,
            color=C_SUBJECT,
            arrowprops={"arrowstyle": "-", "lw": 0.6, "color": C_SUBJECT},
            zorder=Z_ANNOTATION,
        )

    # A curve that plateaus below 1.0 has not run off the right edge — it never
    # solved those cases at all. Readers new to performance profiles routinely
    # misread this, and it is the difference between "slow" and "failed".
    #
    # Stated in the abstract the caveat was unfalsifiable prose: the only curve
    # in this run that does it misses the ceiling by well under a millimetre in
    # print, so a reader looking for the plateau the caveat warns about finds
    # none and concludes the caveat is boilerplate. Naming the instance and its
    # count is what makes the sentence checkable against the canvas.
    plateau = [(s, *coverage[s]) for s in solvers if coverage[s][0] < coverage[s][1]]
    if plateau:
        named = "; ".join(f"{s} solved {solved} of {total}" for s, solved, total in plateau)
        caveat = (
            f"a curve plateauing below 1.0 means unsolved cases, not a longer tail — here {named}"
        )
    else:
        caveat = (
            "a curve plateauing below 1.0 would mean unsolved cases, not a "
            "longer tail; every curve here reaches 1.0"
        )
    ax.annotate(
        caveat,
        xy=(0.5, -0.230),
        xycoords="axes fraction",
        ha="center",
        fontsize=6.5,
        color=INK_MUTED,
        zorder=Z_ANNOTATION,
    )

    m = summary.get("manifest", {})
    depth = timing_depth(m.get("run_id", ""))
    if depth is not None:
        requested, effective = depth
        ax.annotate(
            f"deepest rung of the repetition ladder: {requested} repetitions "
            f"requested, {effective} effective timed solves per case",
            xy=(0.5, -0.305),
            xycoords="axes fraction",
            ha="center",
            fontsize=6.5,
            color=INK_MUTED,
            zorder=Z_ANNOTATION,
        )

    n_common = coverage[solvers[0]][1]
    # Two lines: one subtitle ran past the right edge and truncated its tail.
    subtitle = (
        f"{n_common} of {summary['n_cases']} cases, those offered to all "
        f"{len(solvers)} backends · baseline {baseline}"
    )
    notes = []
    excluded = [s for s in summary["solvers"] if s not in solvers]
    if excluded:
        detail = ", ".join(
            f"{s} (offered {eligible.get(s, 0)}/{summary['n_cases']})" for s in excluded
        )
        notes.append(f"excluded from the profile, partial coverage: {detail}; see text")
    if dropped:
        # No best time exists for such a case, so it cannot enter a ratio. Its
        # count is stated rather than absorbed silently into the denominator.
        notes.append(f"{dropped} further case(s) omitted: no plotted backend succeeded")
    second = "; ".join(notes)
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
        ncol=2,
        columnspacing=1.8,
        handlelength=2.6,
        bbox_to_anchor=(0.5, 0.0),
    )
    fig.subplots_adjust(left=0.085, right=0.98, top=0.90, bottom=0.32)
    for ext, dpi in (("pdf", 300), ("png", 300)):
        fig.savefig(HERE / f"{STEM}.{ext}", dpi=dpi)

    # The plateau caveat is worth its line only because the gap it names is too
    # small to see; the receipt states the gap in printed pixels so that claim
    # is itself checkable.
    bbox = ax.get_window_extent()
    plt.close(fig)

    print(f"wrote {STEM}.pdf / .png")
    print(f"  {n_common} of {summary['n_cases']} cases, offered to all {len(solvers)} backends")
    print(f"  tau axis 1.0 to {tau_max:.6f} (true maximum ratio; no crop)")
    if depth is not None:
        print(f"  timing depth {depth[0]} repetitions requested / {depth[1]} effective")
    else:
        print("  timing depth unavailable; the depth line is omitted from the canvas")
    if dropped:
        print(f"  {dropped} case(s) omitted: no plotted backend succeeded")
    for s in excluded:
        print(f"  {s:20s} excluded, offered {eligible.get(s, 0)}/{summary['n_cases']}")
    for s in solvers:
        solved, total = coverage[s]
        gap_px = (1.0 - solved / total) / 1.02 * bbox.height
        note = f"  <- plateaus {gap_px:.2f} px below the ceiling" if solved < total else ""
        print(
            f"  {s:20s} {solved:4d}/{total} solved · fastest outright {efficiency[s]:.6f}{note}",
        )


if __name__ == "__main__":
    plot(load_summary())
