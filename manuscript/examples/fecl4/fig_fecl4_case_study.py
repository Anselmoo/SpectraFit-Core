"""Figure: Fe L2,3-edge XAS case study — [FeCl4]- (d5) vs [FeCl4]2- (d6).

Fits both measured spectra in `manuscript/examples/fecl4/` with spectrafit-core and renders
the manuscript's real-data case-study figure plus a machine-readable results file
the manuscript text quotes its numbers from.

Reproduce from a clean clone:

    uv sync --group manuscript
    uv run --with maturin maturin develop --release
    uv run --group manuscript python manuscript/examples/fecl4/fig_fecl4_case_study.py

Outputs (written next to this file):
    fig_fecl4_case_study.pdf   vector, for submission
    fig_fecl4_case_study.png   300 dpi raster, for preview
    fecl4_fit_results.json     selected fit + the full model-selection comparison

Physical model, per spectrum
----------------------------
Pseudo-Voigt peaks across the L3 and L2 multiplets, on top of two `arctan_step`
continuum edge jumps and a constant offset. The two step amplitudes are not
independent: the 2p3/2 : 2p1/2 initial states carry a statistical 2:1
degeneracy, so the L2 edge jump is tied to half the L3 jump through an
expression edge rather than fitted freely. That single `bind()` call removes one
free parameter from every fit and is why the reported step ratio is exactly
2.000 rather than a fitted approximation to it.

Component list and model selection
----------------------------------
The components are specified from the spectroscopy, not chosen by a fit
statistic. d5 carries a tiny pre-shoulder near 706 eV on the rising L3 edge;
d6 carries a pre-shoulder near 705 eV and a post-shoulder near 708 eV. Each is
modelled because it is there.

BIC is still computed, but as a reported diagnostic rather than the selector:
every named shoulder is refitted away and the resulting dBIC recorded in the
JSON. Here the criterion agrees emphatically with all three assignments
(+572, +362, +30). Were it ever to disagree, the disagreement would be
published rather than resolved by deleting the component.

A cautionary result, recorded because it nearly went the other way. An earlier
version of this script let BIC *choose* between an 8- and a 9-component d5
model, seeding the extra peak at 706.3 eV with sigma 0.4. BIC rejected it
(dBIC +16.8 against). That verdict was an artefact of the seed, not a property
of the data: re-seeded at 706.0 with sigma 0.35, from the spectroscopic
assignment rather than from a guess, the same criterion now favours the same
component by +572, and chi2_red drops six-fold from 0.0425 to 0.0071. An
information criterion evaluates the optimum a solver actually reached, so on a
multi-modal surface it silently scores the starting point as much as the model.
This is the argument for specifying components from the spectroscopy and using
the criterion to check them, rather than the reverse.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import matplotlib as mpl
import numpy as np
from matplotlib import pyplot as plt
from matplotlib.ticker import MultipleLocator
from spectrafit_core import (
    FitOptions,
    MeasurementData,
    arctan_step,
    compose,
    constant,
    fit,
    pseudo_voigt,
)

HERE = Path(__file__).resolve().parent
DATA = HERE

# Fitted window. The measured files span 660-830 eV, but only the Fe L2,3
# white-line region carries the multiplet structure this case study is about;
# the 660-695 eV pre-edge hump and the >735 eV tail are outside the model and
# are deliberately not fitted rather than absorbed into a wider background.
WINDOW = (698.0, 735.0)

# Chart series ramp from docs/stylesheets/tokens/palette.css (--c-chart-*).
#
# Not the raw `--c-<backend>` brand colours: those are a UI palette, where each
# hue sits beside its own label and is compared with one neighbour at a time. A
# plot is the opposite — every series competes with every other at once, and
# measured all-pairs the brand ramp collapses (systemIndigo vs systemBlue is
# dE 0.8 deutan). Deuteranopia merges red/green/orange into one family and
# blue/indigo/cyan into another, so Apple's system set yields at most two
# separable hues however they are chosen. The `--c-chart-*` ramp is the
# documented extension for exactly this case: corporate-adjacent, darkened
# until every entry is legal as a stroke, and picked for pairwise separation.
#
# Validator (light surface, --pairs all): lightness PASS, chroma PASS,
# normal-vision floor PASS (worst 17.7), contrast PASS (all >= 3:1), CVD WARN
# at 7.0 deutan — inside the 6-8 floor band, legal only with secondary
# encoding. Hence the redundancy below: the total model is also the thickest
# line, the edge steps are also the only dashed one, and L3/L2 are additionally
# separated by sitting in disjoint energy ranges.
C_FIT = "#b03a8f"  # --c-chart-4 — total model (thickest stroke)
C_L3 = "#0067d6"  # --c-chart-1 — L3 multiplet components
C_L2 = "#00875f"  # --c-chart-3 — L2 multiplet components
C_STEP = "#9c5f00"  # --c-chart-2 — arctan continuum steps (dashed)
INK = "#1d1d1f"
INK_MUTED = "#6e6e73"
GRID = "#e3e3e0"

# Peak seeds are (center /eV, amplitude, sigma /eV). The component list is
# specified from the spectroscopy, not chosen by a fit statistic: the author
# identifies a tiny pre-shoulder on the d5 L3 edge near 706 eV and a post-
# shoulder on d6 near 708 eV, and both are modelled because they are there.
#
# BIC is still computed, but as a REPORTED DIAGNOSTIC rather than the selector.
# For each named shoulder the fit is repeated with that component ablated and
# the resulting dBIC written to the JSON. See the module docstring for why the
# order matters: letting BIC choose, from a guessed seed, rejected the d5
# shoulder outright — the same component the spectroscopic seed now supports by
# +572. The criterion scores the optimum the solver reached, not the model.
_D5_PEAKS = [
    (706.0, 1.2, 0.35),  # pre-shoulder (author-identified)
    (707.9, 15.0, 0.45),
    (709.4, 2.0, 0.60),
    (710.4, 2.0, 0.60),
    (711.8, 1.5, 0.80),
    (713.4, 2.4, 0.90),
    (720.4, 2.6, 0.80),
    (721.7, 2.8, 0.80),
    (723.5, 1.0, 1.00),
]
_D6_PEAKS = [
    (704.6, 1.0, 0.40),  # pre-shoulder
    (705.9, 11.5, 0.40),
    (707.3, 4.2, 0.50),
    (708.0, 1.5, 0.45),  # post-shoulder (author-identified)
    (709.0, 1.5, 0.70),
    (710.5, 0.7, 0.80),
    (712.0, 0.4, 0.90),
    (717.9, 2.0, 0.70),
    (718.9, 2.7, 0.70),
    (720.6, 1.3, 0.90),
]

SPECTRA: dict[str, dict[str, Any]] = {
    "d5": {
        "file": "FeCl4_d5.txt",
        "label": r"[FeCl$_4$]$^{-}$  (Fe$^{3+}$, $d^5$)",
        "step_l3": 708.5,
        "step_l2": 721.5,
        "peaks": _D5_PEAKS,
        "l3_count": 6,
        # name -> index in `peaks` to remove for the diagnostic refit
        "ablations": {"pre-shoulder 706 eV": 0},
    },
    "d6": {
        "file": "FeCl4_d6.txt",
        "label": r"[FeCl$_4$]$^{2-}$  (Fe$^{2+}$, $d^6$)",
        "step_l3": 706.5,
        "step_l2": 719.5,
        "peaks": _D6_PEAKS,
        "l3_count": 7,
        "ablations": {"pre-shoulder 705 eV": 0, "post-shoulder 708 eV": 3},
    },
}


def load(path: Path) -> tuple[np.ndarray, np.ndarray]:
    r"""Read a two-column energy/intensity spectrum, restricted to `WINDOW`.

    The measured files use classic-Mac carriage-return line endings, so the
    split is on ``[\r\n]+`` rather than on ``\n``; reading them with plain
    ``readlines()`` yields a single 691-record line. The energy grid is *not*
    uniform — roughly 0.11 eV across the white lines and coarser in the
    background — so the window holds 331 points, not the 149 a uniform 0.25 eV
    step would suggest.
    """
    rows = re.split(r"[\r\n]+", path.read_bytes().decode())
    xy = np.array([[float(p[0]), float(p[1])] for p in (r.split() for r in rows if r.strip())])
    mask = (xy[:, 0] >= WINDOW[0]) & (xy[:, 0] <= WINDOW[1])
    return xy[mask, 0], xy[mask, 1]


def build(spec: dict, peaks: list) -> Any:
    """Compose the multiplet + edge-step model graph for a given peak list."""
    nodes = [
        pseudo_voigt(
            f"p{i}",
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
        for i, (cen, amp, sig) in enumerate(peaks)
    ]
    for key, amp0 in (("step_l3", 0.30), ("step_l2", 0.15)):
        cen = spec[key]
        nodes.append(
            arctan_step(
                key,
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
    nodes.append(constant("bg", c=0.0))
    # Statistical 2p3/2 : 2p1/2 = 2:1 edge-jump branching ratio, imposed as an
    # expression edge instead of a free parameter.
    return compose(nodes).bind("step_l3.amplitude / 2", to="step_l2.amplitude").build()


def run_fit(spec: dict, peaks: list) -> Any:
    """Fit one candidate model; raise rather than report a non-converged fit."""
    x, y = load(DATA / spec["file"])
    result = fit(
        build(spec, peaks),
        MeasurementData(x=x.tolist(), y=y.tolist()),
        FitOptions(solver="lm", max_iterations=2000, tolerance=1e-10),
    )
    if not result.success:
        msg = f"{spec['file']}: fit did not converge ({result.message})"
        raise RuntimeError(msg)
    return result


def fit_with_ablations(spec: dict) -> dict:
    """Fit the author-specified model, then refit with each named shoulder removed.

    The reported model is always the full one. The ablations exist to quantify
    what each named shoulder is worth: dBIC = BIC(without) - BIC(full), so a
    NEGATIVE value means the criterion prefers the model without that component.

    BIC rather than AIC for the diagnostic: the comparison differs by a whole
    peak (four parameters), and with 331 points BIC's stiffer complexity penalty
    is the conservative choice — it is the criterion that can actually argue
    against a component, which is the only thing worth reporting here.
    """
    x, y = load(DATA / spec["file"])
    full = run_fit(spec, spec["peaks"])

    ablations = {}
    for name, index in spec.get("ablations", {}).items():
        reduced = [pk for i, pk in enumerate(spec["peaks"]) if i != index]
        r = run_fit(spec, reduced)
        ablations[name] = {
            "n_peaks": len(reduced),
            "r_squared": r.r_squared,
            "reduced_chi2": r.reduced_chi2,
            "bic": r.bic,
            "delta_bic_vs_full": r.bic - full.bic,
            "prefers_full": r.bic > full.bic,
        }

    return {
        "x": x,
        "y": y,
        "spec": spec,
        "peaks": spec["peaks"],
        "result": full,
        "ablations": ablations,
    }


def _l3_white_line(res: Any, n_l3: int):
    """Return the ParameterResult for the tallest L3 component's centre."""
    best_i, best_amp = 0, -1.0
    for i in range(n_l3):
        amp = res.parameters[f"p{i}.amplitude"].value
        if amp > best_amp:
            best_i, best_amp = i, amp
    return res.parameters[f"p{best_i}.center"]


def plot(fits: dict[str, dict], out_stem: Path) -> None:
    """Render the two-column, two-row case-study figure."""
    mpl.rcParams.update(
        {
            "font.size": 8,
            "axes.labelsize": 8,
            "axes.titlesize": 9,
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
    fig, axes = plt.subplots(
        2,
        2,
        figsize=(7.0, 4.3),
        sharex="col",
        gridspec_kw={"height_ratios": [3.2, 1.0], "hspace": 0.06, "wspace": 0.18},
    )

    for col, state in enumerate(("d5", "d6")):
        f = fits[state]
        x, y, res = f["x"], f["y"], f["result"]
        n_l3 = f["spec"]["l3_count"]
        n_peaks = len(f["peaks"])
        ax, axr = axes[0, col], axes[1, col]

        # Components grouped by physical identity — one hue per multiplet, not
        # one hue per node (nine cycled hues would encode nothing).
        for i in range(n_peaks):
            ax.plot(
                x,
                np.asarray(res.components[f"p{i}"]),
                lw=0.7,
                color=C_L3 if i < n_l3 else C_L2,
                alpha=0.9,
            )
        ax.plot(
            x,
            np.sum([np.asarray(res.components[k]) for k in ("step_l3", "step_l2", "bg")], axis=0),
            lw=1.0,
            ls="--",
            color=C_STEP,
        )
        ax.plot(x, y, ls="none", marker="o", ms=2.0, mfc="none", mew=0.5, color=INK_MUTED)
        ax.plot(x, np.asarray(res.best_fit), lw=1.6, color=C_FIT)

        ax.set_ylim(-0.9, max(y) * 1.14)
        ax.grid(True, color=GRID, lw=0.5)
        ax.set_axisbelow(True)
        ax.set_title(f["spec"]["label"], color=INK, pad=6)
        # The L3 white line is the tallest component, not a fixed index —
        # adding a pre-shoulder shifted it, and hardcoding an index silently
        # annotated the shoulder instead.
        centre = _l3_white_line(res, n_l3)
        ax.annotate(
            f"L$_3$ max {centre.value:.2f} eV",
            xy=(centre.value, max(y)),
            xytext=(centre.value + 3.4, max(y) * 0.94),
            color=INK,
            arrowprops={"arrowstyle": "-", "lw": 0.6, "color": INK_MUTED},
        )
        ax.text(
            0.975,
            0.62,
            f"$R^2$ = {res.r_squared:.4f}\n{n_peaks} peaks, {res.n_iter} iterations",
            transform=ax.transAxes,
            ha="right",
            va="top",
            color=INK_MUTED,
        )

        axr.axhline(0.0, lw=0.6, color=INK_MUTED)
        axr.plot(x, np.asarray(res.residuals), lw=0.8, color=INK)
        axr.grid(True, color=GRID, lw=0.5)
        axr.set_axisbelow(True)
        axr.set_xlabel("Incident photon energy (eV)")
        axr.set_xlim(*WINDOW)
        # 1 eV minor ticks: the multiplet features this figure is about are
        # ~1 eV apart, so the 5 eV majors alone make them hard to place.
        for a in (ax, axr):
            a.xaxis.set_minor_locator(MultipleLocator(1.0))
            a.tick_params(axis="x", which="minor", length=2.0, color=INK_MUTED)
            a.grid(True, which="minor", axis="x", color=GRID, lw=0.3, alpha=0.7)
        if col == 0:
            ax.set_ylabel("Normalised absorption (arb. units)")
            axr.set_ylabel("Residual")

    # One legend for the whole figure: identity is never carried by colour alone.
    handles = [
        plt.Line2D(
            [],
            [],
            ls="none",
            marker="o",
            ms=3.5,
            mfc="none",
            mew=0.6,
            color=INK_MUTED,
            label="Measured",
        ),
        plt.Line2D([], [], lw=1.6, color=C_FIT, label="Total model"),
        plt.Line2D([], [], lw=0.9, color=C_L3, label="L$_3$ multiplet"),
        plt.Line2D([], [], lw=0.9, color=C_L2, label="L$_2$ multiplet"),
        plt.Line2D([], [], lw=1.0, ls="--", color=C_STEP, label="Edge steps + offset (tied 2:1)"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=5,
        frameon=False,
        bbox_to_anchor=(0.5, 0.0),
        columnspacing=1.6,
        handlelength=1.8,
    )
    fig.subplots_adjust(left=0.075, right=0.99, top=0.93, bottom=0.205)
    for ext, dpi in (("pdf", None), ("png", 300)):
        fig.savefig(out_stem.with_suffix(f".{ext}"), dpi=dpi)
    plt.close(fig)


def serialise(fits: dict[str, dict]) -> dict:
    """Collect the numbers the manuscript quotes, plus the selection evidence."""
    out: dict[str, Any] = {
        "window_ev": list(WINDOW),
        "model": (
            "pseudo_voigt multiplet + 2 arctan_step + constant; "
            "L2 step amplitude tied to L3/2 via an expression edge"
        ),
        "selection_criterion": (
            "components specified from the spectroscopy; BIC reported per named "
            "shoulder as an ablation diagnostic, not used to select"
        ),
        "spectra": {},
    }
    for state, f in fits.items():
        res = f["result"]
        out["spectra"][state] = {
            "source_file": f"manuscript/examples/fecl4/{f['spec']['file']}",
            "n_points": len(f["x"]),
            "model": "author-specified components; BIC reported, not selecting",
            "n_peaks": len(f["peaks"]),
            "dof": res.dof,
            "r_squared": res.r_squared,
            "reduced_chi2": res.reduced_chi2,
            "aic": res.aic,
            "bic": res.bic,
            "n_iter": res.n_iter,
            "n_func_evals": res.n_func_evals,
            "n_jac_evals": res.n_jac_evals,
            "condition_number": res.condition_number,
            "message": res.message,
            # Each named shoulder, refitted away, so the reader can weigh it.
            # dBIC = BIC(without) - BIC(full): positive means the criterion
            # agrees the component earns its parameters, negative means it does
            # not and the component is kept on spectroscopic grounds anyway.
            "shoulder_ablations": f["ablations"],
            "parameters": {
                name: {"value": p.value, "stderr": p.stderr, "vary": p.vary, "expr": p.expr}
                for name, p in res.parameters.items()
            },
        }

    def l3_max(state: str):
        f = fits[state]
        return _l3_white_line(f["result"], f["spec"]["l3_count"])

    c5, c6 = l3_max("d5"), l3_max("d6")
    out["l3_chemical_shift_ev"] = {
        "value": c5.value - c6.value,
        "stderr": float(np.hypot(c5.stderr or 0.0, c6.stderr or 0.0)),
        "d5_center": c5.value,
        "d6_center": c6.value,
        "definition": "L3 white-line maximum of d5 minus that of d6",
    }
    return out


def main() -> None:
    """Fit both spectra, render the figure, and write the results JSON."""
    fits = {state: fit_with_ablations(spec) for state, spec in SPECTRA.items()}
    plot(fits, HERE / "fig_fecl4_case_study")
    summary = serialise(fits)
    (HERE / "fecl4_fit_results.json").write_text(json.dumps(summary, indent=2) + "\n")

    for state, f in fits.items():
        res = f["result"]
        print(
            f"{state}: {len(f['peaks'])} peaks  R2={res.r_squared:.6f}  "
            f"chi2_red={res.reduced_chi2:.5g}  dof={res.dof}  iters={res.n_iter}",
        )
        for name, a in f["ablations"].items():
            verdict = (
                "BIC agrees"
                if a["prefers_full"]
                else "BIC DISAGREES (kept on spectroscopic grounds)"
            )
            print(f"    without {name:22s} dBIC={a['delta_bic_vs_full']:+9.1f}  {verdict}")
    sh = summary["l3_chemical_shift_ev"]
    print(f"L3 chemical shift d5-d6 = {sh['value']:.3f} +/- {sh['stderr']:.3f} eV")


if __name__ == "__main__":
    main()
