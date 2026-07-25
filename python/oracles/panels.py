"""Canonical panel registry: every report panel as one PanelSpec record.

Registry-over-map (same convention as oracles.models.MODEL_REGISTRY): the web
PanelRenderer reads these records generically; adding a panel is appending one
record here + (if it needs a new series) one builder in the web
SERIES_REGISTRY. ``source`` strings are contract keys into that web registry --
the fixture test (test_panels.py) and the web sync test (panel_sync.test.ts)
pin the two sides.

Run ``uv run python -m oracles.panels`` after editing DEFAULT_PANELS to
regenerate web/src/fixtures/default_panels.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from oracles.bench_contract import PanelLayout, PanelSpec

_WIDE = PanelLayout(wide=True, height=300)

DEFAULT_PANELS: tuple[PanelSpec, ...] = (
    # -----------------------------------------------------------------------
    # Fit quality
    # -----------------------------------------------------------------------
    PanelSpec(
        id="spectrum",
        title="Spectrum · guess · fit",
        desc="Reference (red), initial guess (dashed), and each backend's fitted curve.",
        chart_kind="line",
        source="spectrumSeries",
        layout=_WIDE,
    ),
    PanelSpec(
        id="residuals",
        title="Residuals",
        desc="Observed − fitted per backend; unstructured scatter about zero means a clean fit.",
        chart_kind="line",
        source="residualSeries",
    ),
    PanelSpec(
        id="peaks",
        title="Per-peak contributions",
        desc="Reconstructed model components, colored by component index.",
        chart_kind="line",
        source="peakSeries",
    ),
    PanelSpec(
        id="ecdf-resid",
        title="Residual calibration (ECDF)",
        desc="Empirical CDF of |residual|/σ — a curve further left is better-calibrated.",
        chart_kind="ecdf",
        source="ecdfResidSeries",
    ),
    # -----------------------------------------------------------------------
    # Parameters & uncertainty
    # -----------------------------------------------------------------------
    PanelSpec(
        id="param-error",
        title="Parameter recovery error",
        desc="Relative error (%) per parameter × backend. Greener is closer to truth.",
        chart_kind="heatmap",
        source="paramErrorMatrix",
    ),
    PanelSpec(
        id="pull-calibration",
        title="Uncertainty calibration (pull)",
        desc="(estimate − truth)/σ; a calibrated solver places ≈68% inside the ±1σ band.",
        chart_kind="violin",
        source="pullRows",
    ),
    PanelSpec(
        id="param-sigma",
        title="Reported parameter σ",
        desc="Fitted 1σ uncertainty per parameter × backend. Lower (greener) is more precise.",
        chart_kind="heatmap",
        source="paramSigmaMatrix",
    ),
    PanelSpec(
        id="corr-matrix",
        title="Parameter correlation",
        desc=(
            "Correlation of the featured backend's parameters. "
            "Strong amplitude–sigma coupling within a peak is expected."
        ),
        chart_kind="heatmap",
        source="corrMatrix",
        layout=PanelLayout(wide=True, height=340),
    ),
    # -----------------------------------------------------------------------
    # Convergence
    # -----------------------------------------------------------------------
    PanelSpec(
        id="convergence",
        title="Convergence",
        desc="Objective cost vs iteration (log). Lower and steeper is better.",
        chart_kind="line",
        source="convSeries",
    ),
    PanelSpec(
        id="gradient",
        title="Gradient norm history",
        desc="‖∇cost‖ over iterations; rapid decay to the floor signals a well-conditioned solve.",
        chart_kind="line",
        source="gradSeries",
    ),
    PanelSpec(
        id="conv-efficiency",
        title="Convergence efficiency",
        desc="Cost reduction per iteration — how much objective each step buys.",
        chart_kind="line",
        source="convEffSeries",
    ),
    # -----------------------------------------------------------------------
    # Reproducibility & stability
    # -----------------------------------------------------------------------
    PanelSpec(
        id="stability-r2",
        title="R² stability vs runs",
        desc="Mean ±1σ band of R² as Monte-Carlo runs accumulate. A tighter band is more reproducible.",
        chart_kind="band",
        source="stabilityR2Bands",
    ),
    PanelSpec(
        id="stability-iters",
        title="Iteration-count stability vs runs",
        desc="Mean ±1σ band of iterations to convergence across repeated runs.",
        chart_kind="band",
        source="stabilityItersBands",
    ),
    PanelSpec(
        id="param-spread",
        title="Estimate spread vs runs",
        desc=(
            "Parameter-estimate spread (mean ±1σ) shrinking as runs accumulate — "
            "the reproducibility envelope."
        ),
        chart_kind="band",
        source="paramSpreadBands",
    ),
    # -----------------------------------------------------------------------
    # Model selection & timing
    # -----------------------------------------------------------------------
    PanelSpec(
        id="model-selection-aic",
        title="Solver-consensus AIC",
        desc=(
            "ΔAIC per backend vs the best-fit AIC in the run. All backends fit the SAME model here; "
            "near-zero means they converged to the same minimum (good — not 'this model is uniquely preferred', "
            "that's classical model selection across different shapes)."
        ),
        chart_kind="lollipop",
        source="modelSelectionAic",
    ),
    PanelSpec(
        id="timing-box",
        title="Runtime stability (box)",
        desc="Per-call runtime distribution over timing repetitions (log). Tight boxes mean predictable latency.",
        chart_kind="box",
        source="timingBoxRows",
    ),
    PanelSpec(
        id="ecdf-time",
        title="Runtime reliability (ECDF)",
        desc="Empirical CDF of per-call runtime per backend.",
        chart_kind="ecdf",
        source="ecdfTimeSeries",
    ),
    PanelSpec(
        id="accuracy-dist",
        title="Accuracy distribution",
        desc="Reduced-χ² spread over repetitions; a narrow violin near 1 is a stable, well-scaled fit.",
        chart_kind="violin",
        source="accuracyRows",
    ),
    PanelSpec(
        id="warmup",
        title="Cold → hot amortization",
        desc="Per-run time as the one-off cost amortizes over many runs (log–log).",
        chart_kind="line",
        source="warmupSeries",
    ),
    PanelSpec(
        id="scaling",
        title="Scaling — runtime vs N",
        desc="Hot runtime vs spectrum length (log–log), with the CPU↔GPU crossover marked.",
        chart_kind="line",
        source="scalingSeries",
    ),
    # -----------------------------------------------------------------------
    # Across the suite
    # -----------------------------------------------------------------------
    PanelSpec(
        id="suite-speed",
        title="Suite speedup distribution",
        desc="Per-backend speedup across all benchmark cases.",
        chart_kind="violin",
        source="suiteSpeedRows",
    ),
    PanelSpec(
        id="suite-accuracy",
        title="Suite accuracy distribution",
        desc="Per-backend R² across all cases — tightly clustered near unity.",
        chart_kind="violin",
        source="suiteAccRows",
    ),
    PanelSpec(
        id="suite-tradeoff",
        title="Accuracy vs speed tradeoff",
        desc="Every case × backend: speedup (x) vs R² (y). Up-and-to-the-right is better.",
        chart_kind="scatter",
        source="suiteTradeoffPoints",
    ),
)


def default_panels() -> list[PanelSpec]:
    """Fresh list copy for report assembly (callers may extend per-run)."""
    return list(DEFAULT_PANELS)


def write_fixture(path: Path | None = None) -> Path:
    """Write the camelCase JSON fixture consumed by the web sync test."""
    target = path or (
        Path(__file__).resolve().parents[2]
        / "web"
        / "src"
        / "fixtures"
        / "default_panels.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [p.model_dump(by_alias=True) for p in DEFAULT_PANELS]
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    print(write_fixture())
