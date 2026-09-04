"""Figure: how much slower than the best, case by case, and where the lead lives.

The figure exists to support one sentence — spectrafit-core is the fastest
backend on 131 of the 151 benchmark cases, the twenty it loses are all one
problem family, and on the rest its lead is a factor rather than a margin.

Panel A answers "who is fast": for every case a backend was offered, one dot at
that backend's median solve time divided by the fastest median any backend
reached on the same case. A dot on the parity rule is a case that backend won
outright. Panel B answers "where the lead lives": for every case, the fastest
competitor's time divided by spectrafit-core's, grouped by problem family, so a
column below parity is a family this library loses.

Reproduce:

    uv run --group manuscript python manuscript/examples/figures/extract_bench_summary.py <run-dir>
    uv run --group manuscript python manuscript/examples/figures/fig_benchmark_profile.py

Outputs, written next to this file:
    fig_benchmark_profile.pdf   vector, for submission
    fig_benchmark_profile.png   300 dpi raster

Why this replaced a Dolan-More performance profile
--------------------------------------------------
The profile was rebuilt from scratch because three of its problems were not
fixable inside it.

First, its denominator was an artefact. A profile needs one case set every
plotted curve was offered, and this suite is ragged on purpose: the four
tied-parameter cases are not handed to SciPy, and the twenty multimodal `optfn`
cases plus those four are not handed to jax. Intersecting five backends gave
147, and the figure had to open by explaining why 147 was not 151. Intersecting
all six gives 127. Neither number is a fact about the library; both are facts
about which subsets happen to overlap.

Second, and worse, 127 is the exact case set on which spectrafit-core is fastest
100 % of the time. The twenty cases it loses are precisely the twenty jax is
never offered. So the one arrangement that lets every backend share a
denominator is also the one that deletes the subject's only weakness, and the
score would rise from 86.8 % to 100 % by discarding the evidence against it.
That is not a figure this paper can print. Scoring each backend over the cases
it was actually offered keeps all 151 and keeps the twenty losses visible, at
the cost of stating a different n per backend — which the axis labels do.

Third, a profile has to be taught before it can be read. Its curve shape is a
cumulative distribution of a ratio, and both canonical readings — the intercept
at tau = 1 and the right-hand asymptote — are properties a reader has to be told
about, which is why the old figure carried a standing caveat under its axis
warning that a curve plateauing below 1.0 meant failure rather than a longer
tail. Drawing the ratios themselves needs no such instruction: a dot on the
parity rule won, a dot above it is that many times slower, and the vertical
spread is the spread.

What is drawn and what is not
-----------------------------
Every case is a dot; nothing is summarised away. The boxes are outline-only and
sit inside their own points, because a filled box hides the densest part of the
sample it claims to describe.

jax is now in the figure. It is offered 127 of 151 and solved all 127 — it never
failed a case it was given, and the old figure's flat exclusion note said so only
in prose. It is fastest on none of them, with a median 4.74x behind the best,
which is a real result and not a structural artefact.

No run identifier appears on the canvas. It named a directory rather than a
quantity, and the reader cannot do anything with it; provenance belongs in the
caption and in `manuscript-state.json`, which carry it. The measurement depth
does appear, because that one is a quantity: this is the deepest rung of the
repetition ladder, 50 effective timed solves per case out of 100 requested.

Quoting the deepest rung needs a word of care, and the canvas gives it one. The
deepest rung is also the most favourable on the geometric mean, which climbs
15.97, 15.78, 16.16, 16.36, 16.45 across the five depths — so naming the depth
without saying what does and does not move with it would be selecting the
flattering measurement quietly. What this figure reports does not move: the win
rate recorded at every one of the five depths is 0.880795 to every digit, and
max |dr2| is 1.284e-04 at all five. The geometric mean, the one quantity that
does drift, is Figure 5's subject and is not quoted here. The depth line is
derived from `ladder.json` at render time and is dropped entirely if the ladder
is not shipped alongside.

The panels are reciprocal for one family only. For `optfn`, panel A's ratio is
spectrafit-core over the winner and panel B's margin is the winner over
spectrafit-core, so those twenty dots are the same twenty numbers inverted. That
is a property of the family being the one it loses, not a duplication: for the
other 131 cases panel A puts spectrafit-core flat on the parity rule and only
panel B shows how far ahead it is.

On colouring the frameworks, twice reversed
-------------------------------------------
A two-panel draft of this figure drew the five comparators in ink and reserved
hue for the subject and for the losing family, on the argument that position
already identifies a backend and a redundant channel is decoration. That was
right for two panels and wrong the moment panel C existed: there a backend is
one line among six sharing a single axis, with no position to be identified by,
and six anonymous grey curves are unreadable however honest they are.

So every framework now carries a hue. The rule the reversal has to respect is
that hue is never the only channel, and it is not: panel A separates the
backends by position, panel C by dash weight and pattern, and panel A's tick
labels are inked in their backend's hue so that axis doubles as panel C's key.
Panel C additionally carries its own six-entry legend, keyed on hue AND dash.
An earlier version had none, arguing the legend would be a second lookup
mechanism for a fact panel A's inked tick labels already carried. Two things
broke that: panel A is not adjacent to panel C -- A and B share the top row and
C is a separate full-width row below a ladder of rotated tick labels -- and the
hue link does not survive greyscale, which is how a reader on paper meets it.
Right-edge direct labels remain rejected, on the original measured grounds that
the five comparators converge inside a pixel of 1.0.

The subject stays outside the chart ramp, on the paper's subject crimson, so
the figure reads as subject-against-field rather than one-of-six.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import numpy as np
from matplotlib import patheffects as pe
from matplotlib import pyplot as plt
from matplotlib.patches import ConnectionPatch, Rectangle

mpl.use("Agg")

HERE = Path(__file__).resolve().parent
SUMMARY = HERE / "bench_summary.json"
# Optional. The sidecar records which run it came from but not how many times
# each case was timed, and "how reliable is this" is the first question a reader
# asks of a timing figure. The depth is read back out of the repetition ladder
# and stated on the canvas; if the ladder is absent the line is dropped rather
# than guessed.
LADDER = HERE.parent / "ladder" / "ladder.json"
RUNGS = HERE.parent / "ladder" / "rungs"
STEM = "fig_benchmark_profile"

# Two hues that are not framework hues, declared first because they carry the
# figure's two cross-panel meanings.
#
# #c1185b is a deliberate positive reuse: it is the subject crimson in
# fig_ladder_stability.py:174 and is spectrafit-core in
# fig_nist_head_to_head.py:41. Same referent, so it is reused on purpose, and it
# is why the subject sits outside the chart ramp below.
#
# #5856d6 is systemIndigo. In fig_ladder_stability.py:175 it carries that
# figure's second axis, the seed sweep; here it carries this figure's second
# axis, the problem family, and specifically the one family the subject loses.
# The role — "the other axis of variation" — is the same, the referent is not,
# so it is declined and renamed here. It is also `--c-scipy-ls-trf` in
# palette.css:105, a backend brand; that backend is drawn in #b03a8f below, so
# the hue is not doing brand duty anywhere on this canvas.
#
# Declined: #d30f45, the reserved attention channel. The element this figure
# wants read first is the `optfn` band, and that band IS a data series — twenty
# cases — so spending the attention hue on it would make it one, which is the
# single thing that hue must never be.
C_SUBJECT = "#c1185b"
C_FAMILY = "#5856d6"

# One hue per framework. This is not the same call the previous version made,
# and the difference is panel C: there each backend is a line among six on one
# axis, with no position to identify it, so hue is the only thing that can. In
# panel A position still identifies the backend and the hue is redundant, which
# is fine -- a channel may be redundant, it may not be absent.
#
# The subject keeps the paper's subject crimson rather than taking a slot in the
# chart ramp, so the reading is subject-against-field and not one-of-six. The
# five comparators take the measured `--c-chart-*` ramp from palette.css, four
# of them at the assignment the previous version used; jax takes `--c-chart-1`,
# which that version had spent on the subject.
#
# Declining, per figure: `--c-chart-1` #0067d6 is lmfit in
# fig_nist_head_to_head.py:42 and Fig 3's L3 multiplet and Fig 6's "Lower" tier
# -- here it is jax. #9c5f00 is the continuum step in Figs 1 and 3 and Fig 6's
# "Average" tier -- here it is lmfit, the timing baseline. #b03a8f is Fig 3's
# total model and Fig 6's "Higher" tier -- here scipy-ls-trf. #00875f is Fig 3's
# L2 multiplet -- here scipy-ls-lm. #4a9fd8 is unique to the ramp.
#
# The ramp's own measured caveats still hold and still need the second channel:
# CVD separation WARN at 7.0 deutan and contrast WARN for chart-5 at 2.82. That
# is why every curve in panel C also carries a distinct dash, why panel A gives
# each backend its own position, and why panel A's tick labels are inked in
# their backend's hue -- so the axis doubles as panel C's key and no separate
# legend is needed to look a curve up.
SERIES_COLOUR = {
    "spectrafit": C_SUBJECT,
    "lmfit": "#9c5f00",
    "jax": "#0067d6",
    "scipy-ls-lm": "#00875f",
    "scipy-ls-trf": "#b03a8f",
    "scipy-ls-dogbox": "#4a9fd8",
}
# Six patterns from distinct classes, not six spacings of the same class: this is
# the channel that has to carry panel C in greyscale, where the hues collapse.
# scipy-ls-lm was (1, 2), a fine dot separated from jax's (1, 1.6) by spacing
# alone -- the two curves and their two legend keys were indistinguishable once
# desaturated. It is now dot-dot-dash, a different pattern class from both jax's
# pure dot and scipy-ls-trf's long-dash-dot.
DASHES = {
    "spectrafit": (None, None),
    "lmfit": (6, 2),
    "jax": (1, 1.6),
    "scipy-ls-lm": (1, 1.8, 1, 1.8, 7, 1.8),
    "scipy-ls-trf": (9, 2, 1, 2),
    "scipy-ls-dogbox": (3, 3),
}
INK = "#1d1d1f"
INK_MUTED = "#6e6e73"
GRID = "#e3e3e0"

# The subject always takes position 0 so the eye starts there; the rest follow a
# fixed order so a backend never moves between runs.
BACKENDS = [
    "spectrafit",
    "lmfit",
    "jax",
    "scipy-ls-lm",
    "scipy-ls-trf",
    "scipy-ls-dogbox",
]
SUBJECT = "spectrafit"

# The family whose twenty cases are the subject's entire disadvantage, and the
# same twenty jax is never offered. Named once, used by both panels.
LOSING_FAMILY = "optfn"

# Diameter in points of one per-case dot. Panel A draws 869 of them and panel B
# 151, so both are small and translucent enough that overlap reads as shading.
CASE_PT = 2.6
JITTER_W = 0.42

# Golden ratio, the increment of the additive low-discrepancy sequence that
# spreads each cloud. Handed out in ascending order of value, it puts points
# that are adjacent vertically about as far apart horizontally as a
# deterministic rule can — an RNG is not available here because the render
# manifest hashes the PNG byte for byte.
PHI_FRAC = 0.6180339887498949


def load_summary() -> dict:
    """Load the sidecar, failing with the command that produces it."""
    if not SUMMARY.exists():
        msg = (
            f"{SUMMARY} not found — every case, count and ratio on both panels is "
            "read from it, so neither panel can be drawn. Produce it with:\n"
            "  uv run --group manuscript python "
            "manuscript/examples/figures/extract_bench_summary.py <run-dir>"
        )
        raise SystemExit(msg)
    return json.loads(SUMMARY.read_text())


def repetition_depth(run_id: str | None) -> dict | None:
    """How many times each case was timed, read back out of the repetition ladder.

    Returns the matching rung's requested and effective repetition counts, the
    number of depths in the ladder, and whether the recorded win rate is the same
    at every depth — or ``None`` when the ladder is not shipped alongside, so the
    figure drops the line instead of asserting a depth it cannot check.

    The rung directories are named for their effective depth (`rung_050`), and
    only their manifests carry the run id, so the match goes through those.
    """
    if run_id is None or not LADDER.exists() or not RUNGS.is_dir():
        return None
    effective = None
    for manifest in sorted(RUNGS.glob("*/manifest.json")):
        if json.loads(manifest.read_text()).get("run_id") == run_id:
            effective = int(manifest.parent.name.rsplit("_", 1)[-1])
            break
    if effective is None:
        return None
    rungs = json.loads(LADDER.read_text()).get("rungs", [])
    match = [r for r in rungs if r.get("reps_effective") == effective]
    if not match:
        return None
    rates = {r.get("headline", {}).get("spectrafit_win_rate") for r in rungs}
    return {
        "requested": match[0].get("reps_requested"),
        "effective": effective,
        "n_depths": len(rungs),
        "deepest": effective == max(r.get("reps_effective", 0) for r in rungs),
        "win_rate_invariant": len(rates) == 1 and None not in rates,
    }


def golden_jitter(values: np.ndarray, width: float) -> np.ndarray:
    """Deterministic x offsets for a dense point cloud, spread by value order.

    Mirrors `fig_ladder_stability.golden_jitter`: an additive golden-ratio
    sequence handed out in ascending order of *values*, over a stable argsort so
    ties cannot permute between runs.
    """
    seq = ((np.arange(len(values), dtype=float) * PHI_FRAC) % 1.0 - 0.5) * width
    out = np.empty(len(values), dtype=float)
    out[np.argsort(values, kind="stable")] = seq
    return out


def timings(case: dict) -> dict[str, float]:
    """Median solve times for the backends that were offered *case* and solved it.

    A backend absent from `m` was never asked to run the case; one present but
    unsuccessful was asked and failed. Neither can contribute a time, but only
    the second is a failure, and the two are counted apart everywhere below.
    """
    return {
        b: float(m["med_ms"])
        for b in BACKENDS
        if (m := case["m"].get(b)) and m.get("success") and m.get("med_ms")
    }


def ratios_by_backend(cases: list[dict]) -> tuple[dict[str, np.ndarray], dict[str, list]]:
    """Per backend: its solve time over the best any backend reached on that case.

    Each backend is scored over the cases it was actually offered, so the arrays
    have different lengths on purpose — that raggedness is the suite's design,
    and forcing a shared denominator is what made the previous version quote a
    case count no reader could place.
    """
    out: dict[str, list[float]] = {b: [] for b in BACKENDS}
    families: dict[str, list] = {b: [] for b in BACKENDS}
    for case in cases:
        times = timings(case)
        if not times:
            continue
        best = min(times.values())
        for b, value in times.items():
            out[b].append(value / best)
            families[b].append(case.get("category"))
    return {b: np.asarray(v, dtype=float) for b, v in out.items()}, families


def margins_by_family(cases: list[dict]) -> dict[str, np.ndarray]:
    """Per family: the fastest competitor's time over the subject's, per case.

    Above 1 the subject is ahead by that factor; below 1 it is behind. Cases the
    subject did not solve, or that no competitor solved, cannot form a margin and
    are skipped rather than given a stand-in value.
    """
    out: dict[str, list[float]] = {}
    for case in cases:
        times = timings(case)
        mine = times.get(SUBJECT)
        rivals = [v for b, v in times.items() if b != SUBJECT]
        if mine is None or not rivals:
            continue
        out.setdefault(case.get("category"), []).append(min(rivals) / mine)
    return {k: np.asarray(v, dtype=float) for k, v in out.items()}


def outline_box(ax: plt.Axes, x: float, col: np.ndarray, width: float) -> None:
    """One outline-only box-and-whisker at *x*, drawn over its own points.

    No fill, for the reason `fig_ladder_stability._box` gives: the whole point of
    a scattered box is that the raw sample stays visible, and a filled box hides
    the densest part of what it summarises. Whiskers reach 1.5x IQR; points
    beyond them are already drawn individually, so no flier markers are added.
    """
    q1, med, q3 = (float(v) for v in np.percentile(col, [25, 50, 75]))
    reach = 1.5 * (q3 - q1)
    lo = float(col[col >= q1 - reach].min())
    hi = float(col[col <= q3 + reach].max())
    ax.plot([x, x], [lo, q1], lw=0.8, color=INK, zorder=5)
    ax.plot([x, x], [q3, hi], lw=0.8, color=INK, zorder=5)
    for cap in (lo, hi):
        ax.plot([x - width * 0.22, x + width * 0.22], [cap, cap], lw=0.8, color=INK, zorder=5)
    ax.add_patch(
        Rectangle(
            (x - width / 2, q1),
            width,
            q3 - q1,
            facecolor="none",
            edgecolor=INK,
            lw=0.9,
            zorder=5,
        ),
    )
    ax.plot([x - width / 2, x + width / 2], [med, med], lw=1.5, color=INK, zorder=6)


def _backend_panel(
    ax: plt.Axes,
    ratios: dict[str, np.ndarray],
    families: dict[str, list],
    n_cases: int,
) -> tuple[float, float]:
    """Panel A: every offered case as one dot, at its ratio to the best on that case.

    Returns the `optfn` band's range inside the subject's cloud, which the
    connectors carry into panel B.
    """
    band = (float("inf"), float("-inf"))
    for x, backend in enumerate(BACKENDS):
        col = ratios[backend]
        subject = backend == SUBJECT
        colour = SERIES_COLOUR[backend]
        jitter = golden_jitter(col, JITTER_W)
        # The losing family is picked out ONLY inside the subject's cloud. Those
        # twenty dots are the whole of its disadvantage and the band the
        # connectors carry into panel B; drawing the same family in the five
        # comparator clouds too was tested and made the hue mean "optfn" rather
        # than "the cases the subject loses", which is the reading that matters.
        flag = np.asarray([f == LOSING_FAMILY for f in families[backend]]) & subject
        for mask, hue, alpha, zorder in (
            (~flag, colour, 0.42 if subject else 0.30, 2),
            (flag, C_FAMILY, 0.9, 4),
        ):
            if not mask.any():
                continue
            ax.plot(
                x + jitter[mask],
                col[mask],
                "o",
                ms=CASE_PT,
                mfc=hue,
                mec="none",
                alpha=alpha,
                ls="none",
                zorder=zorder,
            )
        if subject and flag.any():
            band = (float(col[flag].min()), float(col[flag].max()))
        outline_box(ax, x, col, 0.46)

    ax.axhline(1.0, lw=1.0, color=INK, alpha=0.75, zorder=3)
    # Anchored at the left spine rather than mid-panel, where it landed on the
    # scipy clouds. The white halo is the gold standard's device for text that
    # has to survive whatever it lands on.
    ax.annotate(
        "parity — fastest on this case",
        xy=(-0.55, 1.0),
        xytext=(0, 7),
        textcoords="offset points",
        ha="left",
        fontsize=6.4,
        color=INK,
        zorder=9,
        path_effects=[pe.withStroke(linewidth=2.0, foreground="white")],
    )
    ax.set_yscale("log")
    ax.set_xlim(-0.62, len(BACKENDS) - 0.38)
    ax.set_xticks(range(len(BACKENDS)))
    # Rotated: six backend names side by side overlapped badly when horizontal,
    # and the win count has to stay next to the name it belongs to.
    ax.set_xticklabels(
        [f"{b}  {int((ratios[b] == 1.0).sum())}/{len(ratios[b])} won" for b in BACKENDS],
        fontsize=6.4,
        rotation=30,
        ha="right",
        rotation_mode="anchor",
    )
    # Each label is inked in its own backend's hue, which makes this axis the key
    # for panel C as well and saves that panel a legend it has no room for.
    for tick, backend in zip(ax.get_xticklabels(), BACKENDS, strict=True):
        tick.set_color(SERIES_COLOUR[backend])
    # The violet dots are a meaning-carrying encoding -- the twenty optfn cases,
    # the whole of the subject's disadvantage, and the band the connectors carry
    # into panel B -- and they were drawn with no key at all. Worse, they sit in
    # the subject's own column, so the one hue link the figure declares (a tick
    # label inked in its backend's colour) is contradicted exactly where a reader
    # checks it first: the tick reads crimson, the visible cloud above it reads
    # violet. Naming it here costs one line and closes both.
    n_losing = sum(f == LOSING_FAMILY for f in families[SUBJECT])
    ax.annotate(
        f"violet — the {n_losing} {LOSING_FAMILY} cases,\nthe subject's whole disadvantage",
        xy=(0.0, 1.0),
        xycoords=("data", "axes fraction"),
        xytext=(0, -20),
        textcoords="offset points",
        ha="left",
        va="top",
        fontsize=6.2,
        color=C_FAMILY,
        zorder=9,
        path_effects=[pe.withStroke(linewidth=2.0, foreground="white")],
    )
    ax.set_ylabel("times slower than the best backend on the same case")
    # "every case drawn" was false: a backend's cloud holds the cases it SOLVED,
    # which is 127 for jax (never offered 24) and 146 for scipy-ls-lm (offered
    # 147, no convergence on OF-005). Each tick already prints its own n; the
    # title now says what that n counts instead of overriding it with a claim
    # that only holds for two of the six.
    ax.set_title(
        f"A · backend — {len(BACKENDS)} backends, {n_cases} cases; tick n = solved",
        fontsize=7.2,
        color=INK_MUTED,
        loc="left",
        pad=7,
    )
    return band


def _profile_panel(ax: plt.Axes, ratios: dict[str, np.ndarray], tau_max: float) -> None:
    """Panel C: the cumulative reading of panel A, on panel A's own scale.

    This is a Dolan-More performance profile, and it is deliberately not lettered
    as a third axis of variation: it plots no quantity panel A does not already
    contain. Panel A shows where each backend's cases lie; this shows how quickly
    that mass accumulates, which is the reading a profile is good at and a cloud
    is not. Its x axis IS panel A's y axis -- same ratio, same log scale, same
    parity value -- so the two are one measurement seen along two directions
    rather than two plots stacked.

    Each backend is drawn over the cases it was offered, the same ragged
    convention panel A uses, so this panel introduces no denominator that is not
    already printed on panel A's tick labels. The strict common-set form, which
    needs an intersection, is the appendix figure.
    """
    tau = np.logspace(0, np.log10(max(tau_max, 2.0)), 400)
    handles = []
    for backend in BACKENDS:
        col = ratios[backend]
        subject = backend == SUBJECT
        dash = DASHES[backend]
        (line,) = ax.plot(
            tau,
            [(col <= t).sum() / len(col) for t in tau],
            lw=1.9 if subject else 1.1,
            color=SERIES_COLOUR[backend],
            dashes=dash if dash[0] is not None else (None, None),
            alpha=1.0 if subject else 0.9,
            solid_capstyle="round",
            zorder=4 if subject else 2,
            label=f"{backend}  (n={len(col)})",
        )
        handles.append(line)
    # This panel carries its own legend. The previous version had none, on the
    # premise that "panel A sits directly above on this same scale, its tick
    # labels are inked in these hues, and that axis is the key". Both halves of
    # that failed in the rendered figure: panel A is NOT directly above -- A and
    # B share the top row and C is a separate full-width row, with a ladder of
    # 30-degree rotated tick labels between them -- and the hue link does not
    # survive greyscale, which is how a JORS reader on paper meets it. The
    # palette's own measured CVD/contrast warnings (see SERIES_COLOUR) say the
    # same thing. Six curves with no key on the panel is not a saving.
    #
    # Right-edge direct labels stay rejected, on the original measured grounds:
    # the five comparators converge inside a pixel of 1.0 and their labels
    # collided. The legend goes lower right, where every curve has already risen
    # away and the panel is empty, and it keys BOTH channels -- hue and dash --
    # so it works in colour and in greyscale.
    #
    # n is the count this panel actually accumulates over: cases the backend
    # SOLVED, which is one below what it was offered for scipy-ls-lm (OF-005 did
    # not converge). Printing it here keeps the curve's denominator attached to
    # the curve instead of leaving it to be inferred from panel A.
    ax.legend(
        handles=handles,
        loc="lower right",
        fontsize=6.0,
        frameon=True,
        framealpha=0.92,
        edgecolor=GRID,
        facecolor="white",
        borderpad=0.5,
        labelspacing=0.32,
        handlelength=2.9,
    ).set_zorder(9)
    # tau = 1 IS this panel's left boundary, so the parity "rule" coincides with
    # the spine and cannot be seen as a separate line. It is annotated instead of
    # drawn -- mirroring panel A's parity annotation -- rather than faking a
    # margin below 1, where a performance profile has no domain.
    ax.annotate(
        r"$\tau = 1$ · parity",
        xy=(1.0, 0.0),
        xytext=(3, 4),
        textcoords="offset points",
        ha="left",
        va="bottom",
        fontsize=6.4,
        color=INK,
        zorder=9,
        path_effects=[pe.withStroke(linewidth=2.0, foreground="white")],
    )
    ax.set_xscale("log", base=2)
    ax.set_xlim(1, tau[-1])
    ax.set_ylim(0, 1.02)
    ax.set_xlabel(r"$\tau$ — same ratio as panel A's vertical axis")
    ax.set_ylabel("fraction of that\nbackend's cases")
    ax.set_title(
        "C · the same measurement read cumulatively — how much of each backend's "
        "work is within a factor $\\tau$ of the best",
        fontsize=7.2,
        color=INK_MUTED,
        loc="left",
        pad=7,
    )


def _family_panel(ax: plt.Axes, margins: dict[str, np.ndarray], labels: dict[str, str]) -> None:
    """Panel B: the subject's margin over the fastest competitor, by problem family."""
    order = sorted(margins, key=lambda k: float(np.median(margins[k])))
    for x, family in enumerate(order):
        col = margins[family]
        losing = family == LOSING_FAMILY
        colour = C_FAMILY if losing else C_SUBJECT
        ax.plot(
            x + golden_jitter(col, JITTER_W),
            col,
            "o",
            ms=CASE_PT,
            mfc=colour,
            mec="none",
            alpha=0.85 if losing else 0.42,
            ls="none",
            zorder=4 if losing else 2,
        )
        outline_box(ax, x, col, 0.46)

    ax.axhline(1.0, lw=1.0, color=INK, alpha=0.75, zorder=3)
    ax.set_yscale("log")
    ax.set_xlim(-0.62, len(order) - 0.38)
    ax.set_xticks(range(len(order)))
    # One line per tick: a second "n=" line drifted out of alignment with its own
    # label once rotated, so the count joins the name instead.
    ax.set_xticklabels(
        [f"{labels.get(f, f)}  ({len(margins[f])})" for f in order],
        fontsize=6.4,
        rotation=30,
        ha="right",
        rotation_mode="anchor",
    )
    # Not "times faster": below parity the quantity is a fraction, and calling
    # 0.19 a speed-up in a label that says "faster" reads as a contradiction.
    ax.set_ylabel("subject ÷ best competitor  (>1 ahead)")
    ax.set_title(
        f"B · problem family — {len(order)} families, one dot per case",
        fontsize=7.2,
        color=INK_MUTED,
        loc="left",
        pad=7,
    )


def plot(summary: dict) -> None:
    """Render the two-panel benchmark figure to PDF and 300 dpi PNG."""
    cases = summary["cases"]
    if not cases:
        msg = (
            "the sidecar carries no cases — panel A has nothing to place on the "
            "backend axis and panel B nothing to group by family, so neither "
            "panel exists. Re-run extract_bench_summary.py against a real run."
        )
        raise SystemExit(msg)

    ratios, families = ratios_by_backend(cases)
    drawn = [b for b in BACKENDS if ratios[b].size]
    if len(drawn) < 2:
        msg = (
            f"only {len(drawn)} backend(s) produced a solve time, so there is no "
            "'best backend on the same case' to divide by and the ratio on both "
            "panels is undefined. Check `solvers` in the sidecar."
        )
        raise SystemExit(msg)
    if drawn != BACKENDS:
        missing = ", ".join(b for b in BACKENDS if b not in drawn)
        msg = (
            f"no solve times for {missing} — the backend axis is a fixed roster so "
            "that a backend never moves position between runs, and silently "
            "dropping one would leave the axis claiming a comparison it did not "
            "make. Update BACKENDS deliberately, or use a run that carries it."
        )
        raise SystemExit(msg)

    margins = margins_by_family(cases)
    if LOSING_FAMILY not in margins:
        msg = (
            f"no cases in family {LOSING_FAMILY!r} — it is the band both panels "
            "carry between them and the only family the subject loses, so its "
            "absence changes what the figure claims. Re-check the case catalogue."
        )
        raise SystemExit(msg)

    labels = {c["id"]: c["label"] for c in summary.get("categories", [])}

    mpl.rcParams.update(
        {
            "font.size": 8,
            "axes.labelsize": 7.6,
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
    # Two axes of variation on the top row, and the cumulative re-reading of the
    # left one across the full width beneath it. Panel C is wide because its x
    # axis is panel A's y axis and that scale spans three decades; it is low
    # because a cumulative fraction needs no more height than that.
    fig = plt.figure(figsize=(7.6, 5.9))
    grid = fig.add_gridspec(2, 2, height_ratios=(1.0, 0.68), width_ratios=(1.0, 1.22))
    ax_backend = fig.add_subplot(grid[0, 0])
    ax_family = fig.add_subplot(grid[0, 1])
    ax_profile = fig.add_subplot(grid[1, :])
    # Fixed layout rather than tight_layout, as in fig_ladder_stability: the top
    # two panels carry different quantities on their y axes -- a ratio and its
    # reciprocal -- and a wide gutter with two tick ladders in it is the plainest
    # way to say the scale is not shared.
    # left was 0.085, which clipped the leading "s" of the subject's own rotated
    # tick label against the canvas edge -- in the PDF as well as the PNG, so it
    # shipped. The label is the longest of the six and rotated 30 degrees with
    # ha="right", so it reaches furthest left of anything in the figure.
    fig.subplots_adjust(
        left=0.115,
        right=0.985,
        top=0.925,
        bottom=0.135,
        wspace=0.42,
        hspace=0.66,
    )

    for ax in (ax_backend, ax_family):
        ax.grid(True, axis="y", color=GRID, lw=0.5)
        ax.set_axisbelow(True)
    ax_profile.grid(True, color=GRID, lw=0.5)
    ax_profile.set_axisbelow(True)

    band = _backend_panel(ax_backend, ratios, families, len(cases))
    _family_panel(ax_family, margins, labels)
    _profile_panel(ax_profile, ratios, max(float(r.max()) for r in ratios.values()))

    # No drawn connector between A and C. One was tried and had to cross panel
    # A's rotated tick labels to reach panel C, which cost more legibility than
    # it bought. It is not needed: the carrier is stronger than a line here,
    # because panel A's y axis and panel C's x axis are the same quantity on the
    # same log scale, and the parity value is drawn in both — a rule across A at
    # y = 1 and a rule up C at x = 1, in the same ink. The same number appears in
    # both panels as geometry, which is what the connectors elsewhere exist to
    # achieve by other means.

    # Two connectors carrying the losing family's band out of the subject's cloud
    # in panel A and opening it into panel B, where the same twenty cases are the
    # one column below parity. They are the figure's statement that the two
    # panels are about the same twenty numbers, inverted.
    lose = margins[LOSING_FAMILY]
    for a_edge, b_edge in ((band[0], float(lose.max())), (band[1], float(lose.min()))):
        fig.add_artist(
            ConnectionPatch(
                xyA=(1.0, a_edge),
                coordsA=ax_backend.get_yaxis_transform(),
                xyB=(0.0, b_edge),
                coordsB=ax_family.get_yaxis_transform(),
                color=C_FAMILY,
                lw=0.6,
                alpha=0.55,
                ls=(0, (3.0, 2.0)),
            ),
        )

    won = int((ratios[SUBJECT] == 1.0).sum())
    manifest = summary.get("manifest", {})
    worst_dr2 = manifest.get("max_abs_delta_r2")
    # One line, and it states only what it can prove. An earlier draft said optfn
    # was "the only family jax is not offered", which is false — jax is not
    # offered the four tied-parameter cases either. That belongs to panel A's
    # jax tick label, which carries n=127, and to the caption.
    foot = (
        f"{LOSING_FAMILY} is the only family below parity — "
        f"{won} of {len(ratios[SUBJECT])} cases won"
    )
    if worst_dr2 is not None:
        foot += f" · accuracy invariant, max |$\\Delta r^2$| $\\leq$ {worst_dr2:.1e}"

    # Second line: the measurement depth. A reader's first question of a timing
    # figure is how many times it was timed, and the deepest rung is also the
    # most favourable one on the geometric mean — so quoting the depth without
    # the invariance would be selecting the flattering depth silently. The win
    # rate the ladder records is identical at every depth, which is what makes
    # this figure's counts safe to read off the deepest run; the geometric mean,
    # which does move with depth, is Figure 5's subject and not quoted here.
    depth = repetition_depth(manifest.get("run_id"))
    if depth is not None:
        line = (
            f"{depth['effective']} timed solves per case "
            f"({depth['requested']} requested), the "
            f"{'deepest' if depth['deepest'] else 'selected'} of "
            f"{depth['n_depths']} repetition depths"
        )
        if depth["win_rate_invariant"]:
            line += f"; the recorded win rate is identical at all {depth['n_depths']}"
        # Below the headline: it qualifies that line rather than competing with it.
        fig.text(0.5, 0.012, line, ha="center", va="bottom", fontsize=6.6, color=INK_MUTED)

    fig.text(0.5, 0.030, foot, ha="center", va="bottom", fontsize=6.6, color=INK_MUTED)

    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"{STEM}.{ext}", dpi=300)
    plt.close(fig)

    print(f"wrote {STEM}.pdf / .png")
    print(f"  cases in the suite   {len(cases)}")
    if depth is None:
        print("  repetition depth     UNAVAILABLE — ladder not shipped; line omitted")
    else:
        print(
            f"  repetition depth     {depth['effective']} effective / "
            f"{depth['requested']} requested · deepest {depth['deepest']} · "
            f"{depth['n_depths']} depths · win rate invariant "
            f"{depth['win_rate_invariant']}",
        )
    for b in BACKENDS:
        col = ratios[b]
        offered = sum(b in c["m"] for c in cases)
        print(
            f"  {b:20s} offered {offered:4d} · solved {len(col):4d} · "
            f"won {int((col == 1.0).sum()):4d} · median {np.median(col):.6f}x · "
            f"worst {col.max():.6f}x",
        )
    for family in sorted(margins, key=lambda k: float(np.median(margins[k]))):
        col = margins[family]
        print(
            f"  family {family:12s} n {len(col):4d} · median margin "
            f"{np.median(col):.6f}x · range {col.min():.6f}-{col.max():.6f}x",
        )
    print(f"  carried band         {band[0]:.6f}-{band[1]:.6f}x in A")
    for backend in BACKENDS:
        absent = sorted({c.get("category") for c in cases if backend not in c["m"]})
        if absent:
            print(f"  {backend:20s} never offered families: {', '.join(absent)}")


if __name__ == "__main__":
    plot(load_summary())
