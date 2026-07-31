"""Tie the width of two peaks together with an ``ExprEdge``.

Two overlapping Gaussian peaks are often known, on physical grounds, to
share the same line width — e.g. an instrument's broadening function is
identical for every line it records, even though the lines themselves sit
at different positions with different intensities. Fitting each peak's
``sigma`` independently throws away that prior knowledge and, worse, can let
the optimizer drift the two widths apart in ways the data does not actually
support.

This script ties ``peak2.sigma`` to ``peak1.sigma`` via a graph-level
``ExprEdge`` — the primary surface documented in ``shared_params.md`` — fits
both peaks jointly, and shows the shared width visually as a matching
horizontal "sigma span" annotated between the two peak centers on the plot.

A short second section then re-does the same tie using the equivalent
``Parameter.expr`` surface and asserts the two fits agree to machine
precision, per the "Equivalence guarantee" in ``shared_params.md``.
"""

import numpy as np
from _plotting import plot_fit, savefig
from spectrafit_core import (
    ExprEdge,
    FitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

# --------------------------------------------------------------------------
# Synthesize example data: two Gaussians with identical sigma (0.6),
# but different amplitudes and centers.
# --------------------------------------------------------------------------
rng = np.random.default_rng(42)
x = np.linspace(-2, 4, 120)
sigma_true = 0.6
center1_true, center2_true = 0.0, 2.5
peak1_true = 3.0 * np.exp(-0.5 * ((x - center1_true) / sigma_true) ** 2)
peak2_true = 2.0 * np.exp(-0.5 * ((x - center2_true) / sigma_true) ** 2)
noise = rng.normal(0, 0.05, len(x))
y = peak1_true + peak2_true + noise

# --------------------------------------------------------------------------
# Primary form: ExprEdge (graph-level tie).
#
# Build a FitGraph with two Gaussian peaks and ONE ExprEdge tie:
# peak2.sigma = peak1.sigma (they must be identical).
# --------------------------------------------------------------------------
graph = FitGraph(
    nodes=[
        ModelNodeSpec(
            id="peak1",
            model_type=ModelType.GAUSSIAN,
            parameters={
                "amplitude": Parameter(value=2.5),
                "center": Parameter(value=0.5),
                "sigma": Parameter(value=0.5, min=1e-3),
            },
        ),
        ModelNodeSpec(
            id="peak2",
            model_type=ModelType.GAUSSIAN,
            parameters={
                "amplitude": Parameter(value=2.0),
                "center": Parameter(value=2.0),
                "sigma": Parameter(value=0.5, min=1e-3),
            },
        ),
    ],
    expr_edges=[
        ExprEdge(
            target_node="peak2",
            target_param="sigma",
            expression="peak1.sigma",
        )
    ],
)

# Prepare measurement data.
data = MeasurementData(x=x.tolist(), y=y.tolist())

# Fit!
result = fit(graph, data)

# Inspect the result.
print(f"Success: {result.success}")
print(f"R²: {result.r_squared:.6f}")
print()

# Print parameters.
print("Fitted parameters:")
for param_name, param in sorted(result.parameters.items()):
    stderr_str = f"{param.stderr:8.4f}" if param.stderr is not None else "    tied"
    print(f"{param_name:20s} = {param.value:8.4f} ± {stderr_str}")
print()

# Verify the tie holds: sigma values must be identical.
sigma1 = result.parameters["peak1.sigma"].value
sigma2 = result.parameters["peak2.sigma"].value
print("Tie verification:")
print(f"  peak1.sigma = {sigma1:.8f}")
print(f"  peak2.sigma = {sigma2:.8f}")
print(f"  Difference  = {abs(sigma1 - sigma2):.2e}")

# --------------------------------------------------------------------------
# Equivalent form: Parameter.expr (per-parameter tie).
#
# The same tie can be declared entirely inside the target Parameter itself,
# with no ExprEdge in the graph at all. Per shared_params.md's "Equivalence
# guarantee", both surfaces compile to the same dependency-ordered
# tied-plan, so the fit result must be numerically identical — we assert
# that here rather than just asserting it in prose.
# --------------------------------------------------------------------------
graph_expr = FitGraph(
    nodes=[
        ModelNodeSpec(
            id="peak1",
            model_type=ModelType.GAUSSIAN,
            parameters={
                "amplitude": Parameter(value=2.5),
                "center": Parameter(value=0.5),
                "sigma": Parameter(value=0.5, min=1e-3),
            },
        ),
        ModelNodeSpec(
            id="peak2",
            model_type=ModelType.GAUSSIAN,
            parameters={
                "amplitude": Parameter(value=2.0),
                "center": Parameter(value=2.0),
                # Tie declared inline: peak2.sigma is derived from peak1.sigma.
                "sigma": Parameter(value=0.5, min=1e-3, expr="peak1.sigma", vary=False),
            },
        ),
    ],
    # expr_edges intentionally empty — the tie lives in Parameter.expr only.
)

result_expr = fit(graph_expr, data)

print()
print("Parameter.expr form (equivalence check):")
print(f"  R² (ExprEdge)      = {result.r_squared:.10f}")
print(f"  R² (Parameter.expr) = {result_expr.r_squared:.10f}")

assert result_expr.success
assert abs(result.chi2 - result_expr.chi2) < 1e-6, "chi2 must match across surfaces"
assert abs(sigma1 - result_expr.parameters["peak1.sigma"].value) < 1e-6
assert abs(sigma2 - result_expr.parameters["peak2.sigma"].value) < 1e-6
print("  Both surfaces agree within 1e-6 — equivalence confirmed.")

if __name__ == "__main__":
    # Plot data + fitted curve (ExprEdge form) with the individual peak
    # components overlaid, then layer on a "shared width" annotation: a
    # horizontal double-headed arrow spanning one sigma on each peak, at a
    # matching height, so the equal widths are visually obvious rather than
    # only asserted in the printed diff.
    best_fit = np.array(result.best_fit)
    fig, ax = plot_fit(
        x,
        y,
        best_fit,
        components=result.components,
        title="Two Gaussian peaks with a shared width (tied via ExprEdge)",
    )

    center1_fit = result.parameters["peak1.center"].value
    center2_fit = result.parameters["peak2.center"].value
    amp1_fit = result.parameters["peak1.amplitude"].value
    amp2_fit = result.parameters["peak2.amplitude"].value
    sigma_fit = sigma1  # identical to sigma2 by the tie

    # Draw a matching-width span (±1 sigma) under each peak's apex, at a
    # shared fraction of that peak's own height, plus a callout labeling the
    # tie explicitly.
    for center, amplitude in ((center1_fit, amp1_fit), (center2_fit, amp2_fit)):
        span_height = 0.18 * amplitude
        ax.annotate(
            "",
            xy=(center + sigma_fit, span_height),
            xytext=(center - sigma_fit, span_height),
            arrowprops={"arrowstyle": "<->", "color": "0.25", "lw": 1.4},
        )

    ax.annotate(
        "shared width (σ tied)",
        xy=((center1_fit + center2_fit) / 2, 0.18 * max(amp1_fit, amp2_fit)),
        xytext=(0, 34),
        textcoords="offset points",
        ha="center",
        fontsize=9,
        color="0.25",
    )

    fig.tight_layout()
    savefig(fig, "shared_params")
