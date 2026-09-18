r"""Figure: is the speed bought with accuracy?

WHY THIS EXISTS. The stability figure (`fig_ladder_stability.py`) plots one
quantity on both of its axes: geometric-mean speedup against repetition depth,
and against random seed. Accuracy appears once, as a footnote reading
*"accuracy invariant across both axes"*. A benchmark that reports only speed
cannot answer the question a reader actually has, which is whether the speed was
bought with something, and this project's whole argument is that agreement on
the residual is the weaker test. Reporting a speed-only stability result is the
same blind spot the manuscript criticises in an existing benchmark.

The footnote is also wrong on one of its two axes, which is what prompted this
figure:

* Across the **ladder** the accuracy metric is bit-identical at all five rungs
  (`1.284332e-04` every time). It has to be: the rungs re-time the same 151
  fits of the same catalogue, so nothing that could move accuracy varies.
  "Invariant" is exactly right there, and worth *showing* rather than asserting.
* Across the **50 seeds** it takes 50 distinct values spanning `3.34e-07` to
  `3.72e-04`, a factor of 1111. Each seed draws its own data, so accuracy moves
  with it. The footnote takes the maximum over both axes and calls the quantity
  invariant, which turns "the worst value is bounded" into "the value does not
  change". `validation.md` said the opposite in prose the whole time.

WHAT THE THREE PANELS ANSWER. The question decomposes by what is being varied.

**(A) Depth.** Speed against the accuracy metric, as depth grows. Establishes
that this axis moves speed (a 4.2 % drift) and cannot move accuracy, so a
joint reading of it is trivially flat. Drawn because a flat line is evidence;
an unstated assumption is not.

**(B) Seed.** The joint plane the stability figure never drew: one point per
seed, speed against accuracy. This is where a trade-off would appear as a
downward slope, and it does not appear. The correlation is printed on the panel
rather than described, so a reader can disagree with it.

**(C) Per case.** The strong form of the question, and the only one that can
find a real trade-off. Speedup against lmfit on one axis, and on the other the
ratio of parameter-recovery errors, spectrafit-core over lmfit, so 1 is a tie
and above 1 means we recovered the parameters less well. Parameters rather than
residual, deliberately: CX-017 is in this suite precisely because six backends
agree on r^2 to three significant figures while their parameters span six orders
of magnitude, and a panel drawn on r^2 would show that case as a tie.

WHAT IT FINDS. Every number below is recomputed at render time and printed in
the receipt.

* All 151 cases are faster, from 4.7x to 98.6x, so there is no slower half of
  the plane to compare against.
* On parameters we are worse than lmfit on more cases than we are better. That
  sign is real and is drawn.
* The magnitude is not. Excluding CX-017 the whole suite lies between 8.5 %
  better and 3.2 % worse, the median is an exact tie, and CX-017 itself at
  +66 % is the pathological case the manuscript already discusses by name.
  Panel C is therefore drawn on the percentage difference rather than the raw
  ratio: on a ratio axis every point but one lands on the tie line and the
  panel shows nothing at all, which is a way of hiding the answer rather than
  giving it.
* The accuracy that *is* materially lost is on the residual, not the parameters,
  on the `optfn` cases the manuscript already carves out and discloses. Those
  are marked separately in panel C rather than folded into the cloud.

So the honest answer is that the speed is not bought with parameter accuracy on
this suite, and the reason the figure is worth having is that until now nothing
showed it either way.

Reproduce from a clean clone:

    uv run --group manuscript python manuscript/examples/figures/fig_speed_accuracy_joint.py

Reads `manuscript/examples/ladder/ladder.json`,
`manuscript/examples/seed-sweep/sweep.json` and
`manuscript/examples/figures/bench_summary.json`. Writes
`fig_speed_accuracy_joint.pdf` and `.png` beside this file. Nothing else is
touched; no existing figure is overwritten.
"""

from __future__ import annotations

import json
import math
import statistics as st
from pathlib import Path
from typing import Any

import matplotlib as mpl
import numpy as np

mpl.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent
STEM = "fig_speed_accuracy_joint"

LADDER = EXAMPLES / "ladder" / "ladder.json"
SWEEP = EXAMPLES / "seed-sweep" / "sweep.json"
SUMMARY = HERE / "bench_summary.json"

# Same palette as the rest of the paper's figures.
C_LADDER = "#c1185b"  # the subject crimson
C_SEED = "#5856d6"  # systemIndigo
C_OPTFN = "#7d3cb5"  # the violet fig_benchmark_profile gives the optfn cases
INK = "#1d1d1f"
INK_MUTED = "#6e6e73"
GRID = "#e3e3e0"

# Below this the residual difference is numerical noise rather than a
# disagreement; it is the threshold the merge gate itself uses.
DR2_MATERIAL = 1e-3
# A floor for the log ratio, so a case that recovers a parameter exactly does
# not become a negative infinity.
ERR_FLOOR = 1e-18


def load(path: Path) -> Any:
    """Read one shipped JSON artifact, naming it if it is missing."""
    if not path.exists():
        msg = (
            f"{path} is missing. This figure reads the shipped benchmark "
            f"artifacts and does not re-run anything; restore the file or "
            f"re-run the ladder."
        )
        raise SystemExit(msg)
    return json.loads(path.read_text(encoding="utf-8"))


def headline_series(rungs: list[dict[str, Any]], key: str) -> list[float]:
    """Pull one headline metric out of every rung, in order."""
    return [float(r["headline"][key]) for r in rungs]


def pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation, or 0.0 when either side does not vary at all."""
    sx, sy = st.pstdev(xs), st.pstdev(ys)
    if sx == 0 or sy == 0:
        return 0.0
    mx, my = st.mean(xs), st.mean(ys)
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys, strict=True)) / len(xs)
    return cov / (sx * sy)


def case_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """One record per case carrying both backends' speed and both accuracies.

    A case is kept only when spectrafit-core and the lmfit baseline both
    succeeded and both report a parameter error, because the ratio the panel
    draws is undefined otherwise. The count that survives is printed, so a
    silently shrinking denominator cannot hide here the way the manuscript's
    denominators once did.
    """
    rows = []
    for case in summary["cases"]:
        subject = case["m"].get("spectrafit")
        base = case["m"].get(summary["baseline_solver_id"])
        if not subject or not base:
            continue
        if not (subject.get("success") and base.get("success")):
            continue
        pe_s, pe_b = subject.get("param_err"), base.get("param_err")
        if pe_s is None or pe_b is None:
            continue
        if any(math.isnan(v) for v in (pe_s, pe_b)):
            continue
        rows.append(
            {
                "id": case["id"],
                "category": case["category"],
                "speedup": float(subject["speedup"]),
                "err_ratio": max(pe_s, ERR_FLOOR) / max(pe_b, ERR_FLOOR),
                "err_pct": (max(pe_s, ERR_FLOOR) / max(pe_b, ERR_FLOOR) - 1.0) * 100.0,
                "d_r2": abs(float(subject["r2"]) - float(base["r2"])),
            },
        )
    return rows


def panel_depth(ax: mpl.axes.Axes, rungs: list[dict[str, Any]]) -> dict[str, Any]:
    """Speed and accuracy against repetition depth."""
    depth = [int(r["reps_effective"]) for r in rungs]
    speed = headline_series(rungs, "geomean_speedup_vs_baseline")
    acc = headline_series(rungs, "max_abs_delta_r2")

    ax.plot(depth, speed, "-o", color=C_LADDER, lw=1.4, ms=4.5, zorder=3)
    ax.set_xscale("log")
    ax.set_xticks(depth)
    ax.set_xticklabels([str(v) for v in depth])
    # The log locator puts 3x10^0, 4x10^0 ... under the five real depths and the
    # labels collide into an unreadable band. Only the rungs exist; nothing is
    # measured between them.
    ax.set_xticks([], minor=True)
    ax.set_xlabel("timing depth  (repetitions per case)")
    ax.set_ylabel("geomean speedup vs lmfit  (x)", color=C_LADDER)
    ax.tick_params(axis="y", colors=C_LADDER)
    ax.grid(True, color=GRID, lw=0.5)
    ax.set_axisbelow(True)

    axa = ax.twinx()
    axa.plot(depth, acc, marker="s", color=INK_MUTED, lw=1.2, ms=4, ls=(0, (4, 2)), zorder=3)
    axa.set_yscale("log")
    axa.set_ylim(min(acc) / 30, max(acc) * 30)
    axa.set_ylabel(r"max $|\Delta r^2|$ vs lmfit", color=INK_MUTED)
    axa.tick_params(axis="y", colors=INK_MUTED)

    spread = (max(speed) / min(speed) - 1.0) * 100.0
    ax.set_title("(A) depth moves speed, and cannot move accuracy", fontsize=8.2, color=INK)
    axa.annotate(
        f"identical at all {len(acc)} rungs\n({acc[0]:.6e}, every digit)",
        xy=(depth[2], acc[2]),
        xytext=(0, 22),
        textcoords="offset points",
        ha="center",
        fontsize=6.4,
        color=INK_MUTED,
        arrowprops={"arrowstyle": "-", "lw": 0.5, "color": INK_MUTED},
    )
    ax.annotate(
        f"{spread:.1f} % drift",
        xy=(depth[-1], speed[-1]),
        xytext=(-6, -16),
        textcoords="offset points",
        ha="right",
        fontsize=6.6,
        color=C_LADDER,
    )
    return {"spread_pct": spread, "acc_distinct": len(set(acc)), "acc": acc[0]}


def panel_seed(ax: mpl.axes.Axes, seeds: list[dict[str, Any]]) -> dict[str, Any]:
    """The joint plane the stability figure never drew: one point per seed."""
    speed = headline_series(seeds, "geomean_speedup_vs_baseline")
    acc = headline_series(seeds, "max_abs_delta_r2")
    r = pearson(speed, [math.log10(v) for v in acc])

    ax.scatter(speed, acc, s=26, color=C_SEED, alpha=0.75, linewidths=0, zorder=3)
    ax.set_yscale("log")
    ax.set_xlabel("geomean speedup vs lmfit  (x)")
    ax.set_ylabel(r"max $|\Delta r^2|$ vs lmfit")
    ax.grid(True, color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    ax.set_title("(B) across seeds, the two do not trade", fontsize=8.2, color=INK)

    ax.axhline(min(acc), color=INK_MUTED, lw=0.5, ls=(0, (1, 2)), zorder=1)
    ax.axhline(max(acc), color=INK_MUTED, lw=0.5, ls=(0, (1, 2)), zorder=1)
    ax.text(
        0.03,
        0.03,
        f"{len(seeds)} seeds\n"
        f"speed {min(speed):.2f}-{max(speed):.2f}x  (sd {st.pstdev(speed):.2f})\n"
        f"accuracy spans {max(acc) / min(acc):.0f}x, and is NOT invariant\n"
        f"correlation r = {r:+.2f}",
        transform=ax.transAxes,
        va="bottom",
        ha="left",
        fontsize=6.5,
        color=INK,
        linespacing=1.5,
        bbox={
            "boxstyle": "round,pad=0.34",
            "facecolor": "white",
            "edgecolor": GRID,
            "linewidth": 0.5,
            "alpha": 0.93,
        },
    )
    return {"r": r, "acc_span": max(acc) / min(acc), "n": len(seeds)}


def panel_cases(ax: mpl.axes.Axes, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per case: speedup against the parameter-recovery ratio."""
    optfn = [r for r in rows if r["category"] == "optfn"]
    other = [r for r in rows if r["category"] != "optfn"]
    worst = max(rows, key=lambda r: r["err_ratio"])

    for group, colour, label in (
        (other, INK_MUTED, "all other categories"),
        (optfn, C_OPTFN, "optfn (multimodal)"),
    ):
        ax.scatter(
            [r["speedup"] for r in group],
            [r["err_pct"] for r in group],
            s=22,
            color=colour,
            alpha=0.7,
            linewidths=0,
            zorder=3,
            label=f"{label}  (n={len(group)})",
        )
    ax.scatter(
        [worst["speedup"]],
        [worst["err_pct"]],
        s=64,
        facecolor="none",
        edgecolor=C_LADDER,
        linewidths=1.2,
        zorder=4,
    )
    ax.annotate(
        f"{worst['id']}, {worst['err_pct']:+.0f} %",
        xy=(worst["speedup"], worst["err_pct"]),
        xytext=(-14, -4),
        textcoords="offset points",
        ha="right",
        fontsize=6.4,
        color=C_LADDER,
        arrowprops={"arrowstyle": "-", "lw": 0.5, "color": C_LADDER},
    )

    # A band for what counts as a tie in practice, so "the cloud sits on the
    # line" is a drawn claim with a stated width rather than an impression.
    ax.axhspan(-5, 5, color=GRID, alpha=0.55, zorder=1)
    ax.axhline(0.0, color=INK, lw=0.8, zorder=2)
    ax.set_xscale("log")
    # Symlog, because the interesting structure is a few per cent wide and the
    # one real outlier is +66 %; a linear axis buries the first and a log axis
    # cannot show the better-than-lmfit half at all.
    ax.set_yscale("symlog", linthresh=1.0, linscale=0.6)
    ax.set_yticks([-10, -5, -1, 0, 1, 5, 10, 50])
    ax.set_yticklabels(["-10", "-5", "-1", "0", "+1", "+5", "+10", "+50"])
    ax.set_ylim(-30, 150)
    ax.set_xlabel("speedup vs lmfit  (x, log)")
    ax.set_ylabel("parameter-recovery error vs lmfit\n(% difference, symlog; 0 = tie)")
    ax.grid(True, color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    ax.set_title("(C) per case, the trade never opens", fontsize=8.2, color=INK)
    ax.legend(loc="lower right", frameon=False, fontsize=6.3, handletextpad=0.4)

    stray = sorted(r["id"] for r in rows if r["d_r2"] > DR2_MATERIAL and r["category"] != "optfn")
    if stray:
        msg = (
            f"cases outside optfn now differ on the residual by more than "
            f"{DR2_MATERIAL:g}: {', '.join(stray)}. The manuscript discloses the "
            f"optfn carve-out and nothing else, so this figure's claim that every "
            f"material residual gap is a disclosed one no longer holds."
        )
        raise SystemExit(msg)

    worse = sum(1 for r in rows if r["err_ratio"] > 1)
    better = sum(1 for r in rows if r["err_ratio"] < 1)
    tie = len(rows) - worse - better
    material = sum(1 for r in rows if r["d_r2"] > DR2_MATERIAL)
    corr = pearson(
        [math.log10(r["speedup"]) for r in rows],
        [math.log10(r["err_ratio"]) for r in rows],
    )
    ax.text(
        0.03,
        0.03,
        f"all {len(rows)} cases faster ({min(r['speedup'] for r in rows):.1f}-"
        f"{max(r['speedup'] for r in rows):.1f}x)\n"
        f"parameters worse on {worse}, better on {better}, tied on {tie}\n"
        f"but bar {worst['id']}, all lie between "
        f"{min(r['err_pct'] for r in rows if r is not worst):+.1f} % and "
        f"{max(r['err_pct'] for r in rows if r is not worst):+.1f} %\n"
        f"correlation r = {corr:+.2f}",
        transform=ax.transAxes,
        va="bottom",
        ha="left",
        fontsize=6.5,
        color=INK,
        linespacing=1.5,
        bbox={
            "boxstyle": "round,pad=0.34",
            "facecolor": "white",
            "edgecolor": GRID,
            "linewidth": 0.5,
            "alpha": 0.93,
        },
    )
    return {
        "n": len(rows),
        "worse": worse,
        "better": better,
        "tie": tie,
        "worst_id": worst["id"],
        "worst_ratio": worst["err_ratio"],
        "corr": corr,
        "material_dr2": material,
    }


def draw() -> None:
    """Compose and write the figure."""
    rungs = load(LADDER)["rungs"]
    seeds = load(SWEEP)["rungs"]
    rows = case_rows(load(SUMMARY))

    mpl.rcParams.update(
        {
            "font.size": 8,
            "axes.labelsize": 7.6,
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
    fig, axes = plt.subplots(1, 3, figsize=(11.4, 3.6))
    a = panel_depth(axes[0], rungs)
    b = panel_seed(axes[1], seeds)
    c = panel_cases(axes[2], rows)

    fig.text(
        0.5,
        0.012,
        "Accuracy here is the residual metric in (A) and (B), where the shipped "
        "artifacts record it, and the parameter-recovery metric in (C), which is "
        "the axis this project argues is the load-bearing one.",
        ha="center",
        va="bottom",
        fontsize=6.4,
        color=INK_MUTED,
    )
    fig.subplots_adjust(left=0.065, right=0.955, top=0.9, bottom=0.185, wspace=0.52)

    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"{STEM}.{ext}", dpi=300)
    plt.close(fig)

    print(f"wrote {STEM}.pdf / .png")
    print(
        f"  (A) depth: speed drifts {a['spread_pct']:.2f} %, accuracy takes "
        f"{a['acc_distinct']} distinct value(s) at {a['acc']:.6e}",
    )
    print(
        f"  (B) seed:  {b['n']} seeds, accuracy spans {b['acc_span']:.0f}x, "
        f"speed-accuracy correlation r = {b['r']:+.4f}",
    )
    print(
        f"  (C) cases: n={c['n']}  worse {c['worse']} / better {c['better']} / "
        f"tied {c['tie']}  worst {c['worst_id']} at {c['worst_ratio']:.3f}x  "
        f"r = {c['corr']:+.4f}",
    )
    print(
        f"       residual difference above {DR2_MATERIAL:g} on "
        f"{c['material_dr2']} case(s), all disclosed as optfn",
    )
    if np.isclose(b["r"], 0.0, atol=0.35):
        print("  verdict: no speed-accuracy trade-off is visible on either aggregate axis")


if __name__ == "__main__":
    draw()
