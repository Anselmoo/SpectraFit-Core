"""Command-line entry point for the benchmark engine.

    PYTHONPATH=python uv run python -m oracles.cli run --reps 5 --mc 20
    PYTHONPATH=python uv run python -m oracles.cli gate

``run`` executes the benchmark and writes a run-centric report tree (``results.json``
+ ``manifest.json``); the report is then served at runtime by the FastAPI app
(``oracles.api`` → ``uv run poe serve``) and fetched by the ``web/`` UI — there
is no inlined HTML artifact. ``gate`` enforces the spectrafit-vs-lmfit regression
thresholds against the latest run (used by CI).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import typer
from pydantic import BaseModel, ConfigDict, Field

from oracles.bench_contract import (
    CalibrationResult,
    GateState,
    ManifestSignals,
    NestedAdequacy,
    SpeedInferenceResult,
)
from oracles.engine import build_report
from oracles.stability import (
    build_stability_study,
    render_markdown,
    verdict_line,
)
from oracles.forensics import render_regressions
from oracles.reports import (
    REPORTS_ROOT,
    _worst_gate_state,
    clear_perf_baseline,
    latest_results,
    latest_run_dir,
    read_perf_baseline,
    write_perf_baseline,
    write_run,
)

GateAxisName = Literal[
    "speed", "accuracy", "regressions", "model_selection",
    "sigma_calibration", "speed_inference",
]
"""Pure-function gate-axis identifiers. ``self_perf`` is NOT included here —
it requires filesystem I/O (``read_perf_baseline``) and so lives in the Typer
command wrapper, not in the pure ``_gate_evaluate`` kernel.

``model_selection`` is evidence-conditional: it is only present in a
:class:`GateReport` when ``nested_adequacy`` is passed to ``_gate_evaluate``
— absent evidence does not generate the axis (no pass-by-absence).

``sigma_calibration`` and ``speed_inference`` are likewise evidence-conditional:
only present when their respective inferential-stats records are provided
(mirror ``model_selection`` / W9 — no pass-by-absence)."""

app = typer.Typer(help="spectrafit-core benchmark engine", no_args_is_help=True)


@app.command()
def run(
    reps: int = typer.Option(5, help="Timing repetitions per case."),
    mc: int = typer.Option(
        20, help="Monte-Carlo noise realizations for the featured case."
    ),
    category: str = typer.Option("benchmark", help="Report category subtree."),
) -> None:
    """Run the benchmark and write results.json + manifest.json into a run dir.

    The report is served by the FastAPI app (``poe serve``) and fetched by the web UI;
    nothing is inlined here.
    """
    audit_sink: dict = {}
    report = build_report(n_reps=reps, n_mc=mc, audit_sink=audit_sink)
    run_dir = write_run(report, category=category)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    audit_records = []
    for (cid, bn), entry in audit_sink.items():
        a = entry.get("audit")
        if not a:
            continue
        audit_records.append(
            {
                "case": cid,
                "backend": bn,
                "y": a["y"],
                "fit": a["fit"],
                "sigma": a["sigma"],
                "dof": a["dof"],
                "storedR2": a["stored_r2"],
                "storedChi2Red": a["stored_chi2_red"],
                "storedRmse": a["stored_rmse"],
                "kappa": a["kappa"],
                "mcEsts": a["mc_ests"],
                "mcSes": a["mc_ses"],
                "trueParams": a["true_params"],
            }
        )
    (run_dir / "audit.json").write_text(json.dumps(audit_records), encoding="utf-8")

    from oracles.audit.runner import run_audit

    run_audit(
        run_dir
    )  # recompute wires from the sidecar; inline trust_block into results.json

    typer.echo(f"benchmark complete → {run_dir}")
    typer.echo(
        f"  {manifest['n_cases']} cases · geomean speedup vs lmfit "
        f"{manifest['geomean_speedup_vs_lmfit']:.2f}x · max |Δr²| "
        f"{manifest['max_abs_delta_r2']:.2e} · spectrafit win-rate "
        f"{manifest['spectrafit_win_rate']:.0%}"
    )
    # Summarize backend regressions on one line so the per-case warning spam stops
    # being the only signal — that spam is what tempted the operator to ^C the
    # report_html sequence before it could finish.
    reg_ids = manifest.get("regression_case_ids") or []
    if reg_ids:
        preview = ", ".join(reg_ids[:6]) + ("…" if len(reg_ids) > 6 else "")
        typer.echo(
            f"  {len(reg_ids)} case(s) had backend regressions: {preview} "
            "(see results.json `suite[*].regression`)"
        )
    typer.echo(
        "  serve it for the web UI: uv run poe serve  (then `cd web && npm run dev`)"
    )


def _gate_geomean(manifest: dict) -> float:
    """Read the geomean speedup field, preferring the canonical key.

    Schema 1.1+ writes ``geomean_speedup_vs_baseline``; pre-1.1 manifests on
    disk only have the legacy ``geomean_speedup_vs_lmfit``. The gate must
    tolerate both — a stored result must not stop validating after a contract
    bump. See `DECISIONS.md` 2026-06-06 ADR for the policy.
    """
    return float(
        manifest.get(
            "geomean_speedup_vs_baseline",
            manifest.get("geomean_speedup_vs_lmfit", 1.0),
        )
    )


def _gate_axis_level(
    value: float,
    fail_threshold: float,
    warn_threshold: float | None,
    *,
    higher_is_better: bool,
) -> GateState:
    """Resolve a single gate-axis value to a canonical ``GateState``.

    The direction of the comparison is axis-specific:

    - **speed** (geomean speedup): ``higher_is_better=True`` — a value *below*
      ``fail_threshold`` is a failure; a value *below* ``warn_threshold`` (but
      at or above ``fail_threshold``) is a warning.
    - **accuracy** (max |Δr²|) and **regressions** (count):
      ``higher_is_better=False`` — a value *above* ``fail_threshold`` is a
      failure; a value *above* ``warn_threshold`` (but at or below
      ``fail_threshold``) is a warning.

    Returns a ``GateState`` Literal so ``ty``/pyright can catch drift from the
    canonical ``GATE_STATES`` tuple in ``oracles.bench_contract``.
    """
    if higher_is_better:
        # e.g. geomean speedup: fail if too low, warn if drifting downward
        if value < fail_threshold:
            return "fail"
        if warn_threshold is not None and value < warn_threshold:
            return "warn"
        return "pass"
    else:
        # e.g. max |Δr²|, regression count: fail if too high, warn if creeping up
        if value > fail_threshold:
            return "fail"
        if warn_threshold is not None and value > warn_threshold:
            return "warn"
        return "pass"


# ---------------------------------------------------------------------------
# Plan C2 refactor 2/4 — extract the pure 3-axis gate decision logic from
# the Typer command.
#
# The Typer ``gate`` command is a thin wrapper: load manifest → build
# ``GateThresholds`` from CLI args → call ``_gate_evaluate`` → format the
# returned ``GateReport`` into the human-readable echoes + JSON object →
# pick an exit code. The self-vs-self perf axis stays inline in the Typer
# command because it requires ``read_perf_baseline`` (filesystem I/O) and
# context-mismatch stderr messaging; the pure kernel handles the three
# axes computable from manifest fields alone.
# ---------------------------------------------------------------------------


class GateThresholds(BaseModel):
    """Threshold knobs for the 3-axis gate evaluation.

    Mirrors the ``spc-bench gate --min-geomean / --max-dr2 / --max-regressions``
    Typer flags plus the optional Cycle 28 ``--warn-*`` floors. Defaults match
    the Typer command's defaults so callers can instantiate ``GateThresholds()``
    to get the standard thresholds without repeating them.
    """

    model_config = ConfigDict(extra="forbid")

    min_geomean: float = 1.0
    max_dr2: float = 1e-3
    max_regressions: int = 0
    warn_geomean: float | None = None
    warn_dr2: float | None = None
    warn_regressions: int | None = None


class GateAxisResult(BaseModel):
    """Per-axis verdict — state plus the value and thresholds it was checked against."""

    model_config = ConfigDict(extra="forbid")

    axis: GateAxisName
    state: GateState
    value: float
    threshold: float
    warn_threshold: float | None = None


class GateReport(BaseModel):
    """Pure-function output: per-axis verdicts + overall state + headline numbers.

    The Typer ``gate`` command serialises this into the human-readable echo
    lines and the ``--json`` payload; the self-vs-self perf axis is appended
    by the command wrapper (it requires ``read_perf_baseline`` I/O).
    """

    model_config = ConfigDict(extra="forbid")

    overall: GateState
    axes: list[GateAxisResult]
    regression_ids: list[str] = Field(default_factory=list)
    geomean_speedup: float
    max_abs_delta_r2: float


def _gate_evaluate(
    manifest: dict | ManifestSignals,
    thresholds: GateThresholds,
    *,
    nested_adequacy: NestedAdequacy | None = None,
    calibration: CalibrationResult | None = None,
    speed_inference: SpeedInferenceResult | None = None,
) -> GateReport:
    """Evaluate the 3-axis gate (speed / accuracy / regressions) — pure function.

    No I/O, no printing, no exit. Takes a manifest payload (either the raw
    dict loaded from ``manifest.json`` or a typed ``ManifestSignals``) plus
    the threshold knobs and returns a typed :class:`GateReport`.

    Self-vs-self perf is NOT evaluated here — it requires
    ``read_perf_baseline`` and so stays in the Typer command wrapper.

    When ``manifest`` is a :class:`oracles.bench_contract.ManifestSignals` (which
    carries only a ``regressions`` count, not real case ids), the returned
    ``GateReport.regression_ids`` is a list of synthetic positional sentinels
    (``["#0", "#1", ...]``). Callers that key on real case ids (e.g. CI annotation
    scripts) must pass the raw manifest dict instead.

    ``nested_adequacy`` — when provided, a fourth ``model_selection`` axis is
    added that fails if ``nested_adequacy.recovered_true_order_bic`` is ``False``.
    When absent (``None``, the default), the axis is not included (no
    pass-by-absence — evidence-conditional gate axis, mirrors W9 wire logic).

    ``calibration`` — when provided and not skipped, a ``sigma_calibration`` axis
    is added that fails if ``calibration.passed is False``. When absent (``None``)
    or skipped, the axis is not included (no pass-by-absence, mirrors W9/W10).

    ``speed_inference`` — when provided and not skipped, a ``speed_inference`` axis
    is added that fails if ``speed_inference.passed is False``. When absent (``None``)
    or skipped, the axis is not included (no pass-by-absence, mirrors W9/W11).
    """
    # Normalise the input — accept either a raw dict (the on-disk manifest.json
    # shape, which has extra keys this kernel doesn't read) or a typed
    # ``ManifestSignals`` (the contract shape).
    if isinstance(manifest, ManifestSignals):
        geomean = manifest.geomean_speedup_vs_baseline
        max_dr2 = manifest.max_abs_delta_r2
        # ManifestSignals has only a `regressions: int` count; the typed shape
        # does not carry the per-case ids, so fall back to an empty list and
        # synthesise N anonymous slots so the count-based regression axis still
        # fires correctly.
        reg_ids: list[str] = [f"#{i}" for i in range(manifest.regressions)]
        nonfinite_dr2_ids: list[str] = list(manifest.nonfinite_dr2_case_ids)
    else:
        geomean = _gate_geomean(manifest)
        max_dr2 = float(manifest["max_abs_delta_r2"])
        reg_ids = list(manifest.get("regression_case_ids") or [])
        nonfinite_dr2_ids = list(manifest.get("nonfinite_dr2_case_ids") or [])

    n_reg = len(reg_ids)
    # Per-axis state resolution — direction conventions match the inline
    # CLI logic exactly (speed=higher-is-better, the others=lower-is-better).
    speed_state = _gate_axis_level(
        geomean, thresholds.min_geomean, thresholds.warn_geomean, higher_is_better=True
    )
    accuracy_state = _gate_axis_level(
        max_dr2, thresholds.max_dr2, thresholds.warn_dr2, higher_is_better=False
    )
    # A non-finite |Δr²| is a hard accuracy failure: `_gate_axis_level` compares
    # `value > threshold`, and a sanitized 0.0 (or a NaN) would otherwise pass.
    if nonfinite_dr2_ids:
        accuracy_state = "fail"
    regressions_state = _gate_axis_level(
        float(n_reg),
        float(thresholds.max_regressions),
        float(thresholds.warn_regressions)
        if thresholds.warn_regressions is not None
        else None,
        higher_is_better=False,
    )

    axes: list[GateAxisResult] = [
        GateAxisResult(
            axis="speed",
            state=speed_state,
            value=geomean,
            threshold=thresholds.min_geomean,
            warn_threshold=thresholds.warn_geomean,
        ),
        GateAxisResult(
            axis="accuracy",
            state=accuracy_state,
            value=max_dr2,
            threshold=thresholds.max_dr2,
            warn_threshold=thresholds.warn_dr2,
        ),
        GateAxisResult(
            axis="regressions",
            state=regressions_state,
            value=float(n_reg),
            threshold=float(thresholds.max_regressions),
            warn_threshold=(
                float(thresholds.warn_regressions)
                if thresholds.warn_regressions is not None
                else None
            ),
        ),
    ]

    # Evidence-conditional model_selection axis — only present when nested_adequacy
    # is provided (no pass-by-absence: absent evidence must not inflate the gate).
    if nested_adequacy is not None:
        # BIC governs the axis (consistent model-order estimator).
        # 1.0 = pass threshold (boolean mapped to 0.0/1.0 so _gate_axis_level works).
        bic_value = 1.0 if nested_adequacy.recovered_true_order_bic else 0.0
        ms_state = _gate_axis_level(
            bic_value, fail_threshold=1.0, warn_threshold=None, higher_is_better=True
        )
        axes.append(
            GateAxisResult(
                axis="model_selection",
                state=ms_state,
                value=bic_value,
                threshold=1.0,
            )
        )

    # Evidence-conditional sigma_calibration axis — only present when calibration
    # is provided and not skipped (no pass-by-absence, mirror model_selection/W9).
    if calibration is not None and not calibration.skipped:
        cal_value = 1.0 if calibration.passed else 0.0
        cal_state = _gate_axis_level(
            cal_value, fail_threshold=1.0, warn_threshold=None, higher_is_better=True
        )
        axes.append(
            GateAxisResult(
                axis="sigma_calibration",
                state=cal_state,
                value=cal_value,
                threshold=1.0,
            )
        )

    # Evidence-conditional speed_inference axis — only present when speed_inference
    # is provided and not skipped (no pass-by-absence, mirror model_selection/W9).
    if speed_inference is not None and not speed_inference.skipped:
        sp_value = 1.0 if speed_inference.passed else 0.0
        sp_state = _gate_axis_level(
            sp_value, fail_threshold=1.0, warn_threshold=None, higher_is_better=True
        )
        axes.append(
            GateAxisResult(
                axis="speed_inference",
                state=sp_state,
                value=sp_value,
                threshold=1.0,
            )
        )

    overall = _worst_gate_state([a.state for a in axes])
    return GateReport(
        overall=overall,
        axes=axes,
        regression_ids=reg_ids,
        geomean_speedup=geomean,
        max_abs_delta_r2=max_dr2,
    )


def build_gate_report(
    manifest: dict | ManifestSignals,
    thresholds: GateThresholds,
    *,
    nested_adequacy: "NestedAdequacy | None" = None,
    calibration: "CalibrationResult | None" = None,
    speed_inference: "SpeedInferenceResult | None" = None,
) -> GateReport:
    """Public entry point for the pure gate evaluation kernel.

    Delegates to :func:`_gate_evaluate` with the same arguments.  Exposed
    under a public name so tests and callers outside this module can import a
    stable, non-underscore symbol without relying on the private
    ``_gate_evaluate`` name.

    ``nonfinite_dr2_case_ids`` in the manifest (or on
    :class:`ManifestSignals`) causes the accuracy axis to fail even when
    ``max_abs_delta_r2`` reads as ``0.0`` (the sanitized-NaN scenario).
    """
    return _gate_evaluate(
        manifest,
        thresholds,
        nested_adequacy=nested_adequacy,
        calibration=calibration,
        speed_inference=speed_inference,
    )


@app.command()
def gate(
    min_geomean: float = typer.Option(
        1.0, help="Fail if geomean speedup vs the baseline solver is below this."
    ),
    max_dr2: float = typer.Option(
        1e-3, help="Fail if max |Δr²| vs the baseline solver exceeds this."
    ),
    max_regressions: int = typer.Option(
        0,
        "--max-regressions",
        help=(
            "Fail if more than N cases appear in manifest.regression_case_ids. "
            "Default 0: any backend regression on any case fails the gate."
        ),
    ),
    perf_tolerance: float = typer.Option(
        0.10,
        "--perf-tolerance",
        help=(
            "Self-vs-self perf gate: fail if current geomean / pinned geomean < "
            "(1 - tolerance). Ignored when no `perf_baseline.json` is pinned."
        ),
    ),
    category: str = typer.Option("benchmark", help="Report category subtree."),
    as_json: bool = typer.Option(
        False,
        "--json",
        help=(
            "Emit a single structured JSON object on stdout instead of the "
            "human-readable echo lines. All gate axes + thresholds + failure "
            "messages + regression case IDs surfaced for CI annotation use "
            "(GitHub Actions / GitLab CI per-file feedback). Exit code semantics "
            "are unchanged: 0 = pass, 1 = fail, 2 = missing run."
        ),
    ),
    # ---- Cycle 28 — 3-state gate (PASS / WARN / FAIL) ----------------------
    # Each axis gains an optional WARN threshold sitting between today's
    # hard floor and the headroom. WARN exits 0 (so CI doesn't fail) but
    # stamps `status="warn"` in the JSON and the matching axis's
    # `level="warn"` for amber annotation. Omitting all `--warn-*` flags
    # keeps today's binary PASS/FAIL behaviour bit-for-bit.
    warn_geomean: float | None = typer.Option(
        None,
        "--warn-geomean",
        help=(
            "WARN if geomean speedup is below this but ≥ --min-geomean (the "
            "hard fail floor). Surfaces drift toward the floor without "
            "failing the job. e.g. --min-geomean 1 --warn-geomean 8 → "
            "pass ≥ 8×, warn 1–8×, fail < 1×."
        ),
    ),
    warn_dr2: float | None = typer.Option(
        None,
        "--warn-dr2",
        help=(
            "WARN if max |Δr²| is above this but ≤ --max-dr2. WARN threshold "
            "is STRICTER than fail (smaller number). e.g. --max-dr2 1e-3 "
            "--warn-dr2 1e-4 → pass ≤ 1e-4, warn 1e-4–1e-3, fail > 1e-3."
        ),
    ),
    warn_regressions: int | None = typer.Option(
        None,
        "--warn-regressions",
        help=(
            "WARN if regressions exceed this but ≤ --max-regressions. e.g. "
            "--max-regressions 5 --warn-regressions 0 → pass 0, warn 1–5, "
            "fail > 5."
        ),
    ),
    warn_self_perf: float | None = typer.Option(
        None,
        "--warn-self-perf",
        help=(
            "WARN if current/pinned ratio is below this but ≥ "
            "(1 - --perf-tolerance). e.g. --perf-tolerance 0.10 "
            "--warn-self-perf 0.95 → pass ≥ 0.95, warn 0.90–0.95, "
            "fail < 0.90."
        ),
    ),
) -> None:
    """Regression gate: fail (exit 1) on speed/accuracy/regression/self-perf breakage."""

    def _say(msg: str, err: bool = False) -> None:
        """Human-readable echo — suppressed in --json mode so stdout is parseable."""
        if not as_json:
            typer.echo(msg, err=err)

    # The newest indexed run missing its results.json means write_run aborted mid-flight
    # (a non-finite metric, disk error): gating on the previous run would silently bless
    # stale data, so refuse loudly rather than fall through to an older results.json.
    newest = latest_run_dir(category)
    if newest is not None and not (newest / "results.json").exists():
        msg = (
            f"regression gate: latest run {newest.name} has no results.json — the run "
            "failed to write; refusing to gate on stale data"
        )
        if as_json:
            typer.echo(
                json.dumps({"status": "error", "error": msg, "run_id": newest.name})
            )
        else:
            typer.echo(msg, err=True)
        raise typer.Exit(2)
    path = latest_results(category)
    if path is None:
        msg = f"regression gate: no results under {REPORTS_ROOT / category}"
        if as_json:
            typer.echo(json.dumps({"status": "error", "error": msg}))
        else:
            typer.echo(msg, err=True)
        raise typer.Exit(2)
    manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
    run_id = path.parent.name
    baseline_id = manifest.get("baseline_solver_id", "lmfit")
    # Extract inference evidence from results.json for the evidence-conditional gate
    # axes (W10/W11: sigma_calibration + speed_inference).  Mirrors the extraction
    # pattern in ``oracles.audit.runner`` — camelCase keys, try/except guarded so a
    # missing or malformed inference block never causes a false gate failure.
    _gate_calibration: CalibrationResult | None = None
    _gate_speed_inference: SpeedInferenceResult | None = None
    try:
        _results_raw = json.loads(path.read_text(encoding="utf-8"))
        _inf = _results_raw.get("inference") or {}
        if _inf.get("calibration"):
            _gate_calibration = CalibrationResult.model_validate(_inf["calibration"])
        if _inf.get("speedInference"):
            _gate_speed_inference = SpeedInferenceResult.model_validate(
                _inf["speedInference"]
            )
    except Exception:  # noqa: BLE001  defensive: parse error / missing build
        _gate_calibration = None
        _gate_speed_inference = None
    # Pure-kernel evaluation of the 3 manifest-driven axes (speed / accuracy /
    # regressions). The self-vs-self perf axis is appended below because it
    # requires filesystem I/O (`read_perf_baseline`) and so cannot live in
    # the pure function.
    thresholds = GateThresholds(
        min_geomean=min_geomean,
        max_dr2=max_dr2,
        max_regressions=max_regressions,
        warn_geomean=warn_geomean,
        warn_dr2=warn_dr2,
        warn_regressions=warn_regressions,
    )
    report = _gate_evaluate(
        manifest,
        thresholds,
        calibration=_gate_calibration,
        speed_inference=_gate_speed_inference,
    )
    geomean = report.geomean_speedup
    dr2 = report.max_abs_delta_r2
    reg_ids = report.regression_ids
    by_axis = {a.axis: a for a in report.axes}
    speed_level = by_axis["speed"].state
    accuracy_level = by_axis["accuracy"].state
    regressions_level = by_axis["regressions"].state
    n_reg = len(reg_ids)
    _say(
        f"geomean speedup vs {baseline_id} = {geomean:.2f}x; "
        f"max |Δr²| = {dr2:.2e}; regressions = {n_reg}"
    )
    failures: list[str] = []
    warnings: list[str] = []
    # Per-axis JSON-shape dict (kept for byte-identical `--json` output);
    # the typed `GateAxisResult` carries the same fields but the `--json`
    # consumers (CI scripts) read the legacy key names.
    axes: dict[str, dict] = {
        "speed": {
            "value": geomean,
            "threshold": min_geomean,
            "warn_threshold": warn_geomean,
            "level": speed_level,
            "pass": speed_level == "pass",
        },
        "accuracy": {
            "value": dr2,
            "threshold": max_dr2,
            "warn_threshold": warn_dr2,
            "level": accuracy_level,
            "pass": accuracy_level == "pass",
        },
        "regressions": {
            "value": n_reg,
            "threshold": max_regressions,
            "warn_threshold": warn_regressions,
            "level": regressions_level,
            "pass": regressions_level == "pass",
        },
    }
    if speed_level == "fail":
        failures.append(
            f"spectrafit slower than {baseline_id} overall "
            f"(geomean {geomean:.2f}x < {min_geomean:g})"
        )
    elif speed_level == "warn":
        warnings.append(
            f"spectrafit speed drift: geomean {geomean:.2f}x below warn "
            f"floor {warn_geomean:g}x"
        )
    if accuracy_level == "fail":
        failures.append(f"accuracy parity broken (max |Δr²| {dr2:.2e} > {max_dr2:.0e})")
    elif accuracy_level == "warn":
        warnings.append(
            f"accuracy drift: max |Δr²| {dr2:.2e} above warn floor {warn_dr2:.0e}"
        )
    if regressions_level == "fail":
        preview = ", ".join(reg_ids[:6]) + ("…" if len(reg_ids) > 6 else "")
        failures.append(
            f"{n_reg} case(s) regressed (max allowed {max_regressions}): {preview}"
        )
    elif regressions_level == "warn":
        preview = ", ".join(reg_ids[:6]) + ("…" if len(reg_ids) > 6 else "")
        warnings.append(
            f"{n_reg} case(s) regressed (warn floor {warn_regressions}): {preview}"
        )
    # Self-vs-self perf gate — only fires when a baseline has been pinned. Refuses
    # to compare across mismatched contexts (different baseline solver / category):
    # the pin was honest about its assumptions; do not silently grade against them.
    pin = read_perf_baseline()
    pin_summary: dict | None = None
    if pin is not None:
        if (
            pin.get("category") != category
            or pin.get("baseline_solver_id") != baseline_id
        ):
            _say(
                f"perf baseline pin ({pin.get('run_id')}: category="
                f"{pin.get('category')!r}, baseline={pin.get('baseline_solver_id')!r}) "
                f"does not match current run (category={category!r}, "
                f"baseline={baseline_id!r}); skipping self-perf check",
                err=True,
            )
            pin_summary = {
                "run_id": pin.get("run_id"),
                "matched": False,
                "reason": "context mismatch",
            }
        else:
            pinned_geomean = float(pin.get("geomean_speedup_vs_baseline", 1.0))
            ratio = geomean / pinned_geomean if pinned_geomean > 0 else 1.0
            floor = 1.0 - perf_tolerance
            _say(
                f"pinned baseline {pin.get('run_id')}: {pinned_geomean:.2f}x; "
                f"current/pinned = {ratio:.0%} (floor {floor:.0%})"
            )
            # self-perf: higher-is-better → fail if current/pinned ratio < floor
            self_perf_level: GateState = _gate_axis_level(
                ratio, floor, warn_self_perf, higher_is_better=True
            )
            axes["self_perf"] = {
                "value": ratio,
                "threshold": floor,
                "warn_threshold": warn_self_perf,
                "level": self_perf_level,
                "pass": self_perf_level == "pass",
            }
            pin_summary = {
                "run_id": pin.get("run_id"),
                "matched": True,
                "pinned_geomean": pinned_geomean,
                "ratio": ratio,
                "floor": floor,
            }
            if self_perf_level == "fail":
                failures.append(
                    f"spectrafit regressed vs pinned baseline {pin.get('run_id')} "
                    f"({ratio:.0%} of {pinned_geomean:.2f}x < floor {floor:.0%})"
                )
            elif self_perf_level == "warn":
                warnings.append(
                    f"perf drift vs pinned baseline {pin.get('run_id')}: "
                    f"{ratio:.0%} below warn floor {warn_self_perf:.0%}"
                )

    # Overall status: worst per-axis level via the shared `_worst_gate_state`
    # helper from `oracles.reports` (same `fail > warn > pass` rank as
    # `_compute_default_gate_state`). WARN exits 0 (CI doesn't fail) but the
    # JSON status is `"warn"` so the step-summary block from Cycle 26 renders amber.
    # Note: `failures`/`warnings` lists drive the message emission below; the
    # headline `status` is the canonical worst-of across the collected messages.
    # Fallback to a single ``"pass"`` so the empty case (no axes failed) still
    # resolves cleanly via the same shared helper.
    _level_list: list[GateState] = ["fail"] * len(failures) + ["warn"] * len(warnings)
    _all_levels: Sequence[GateState] = _level_list or ["pass"]
    status: GateState = _worst_gate_state(_all_levels)
    if as_json:
        # Single object on stdout so a CI script can `jq -r '.status'`. All four
        # gate axes plus the regression case IDs are surfaced so the consumer can
        # post per-file annotations (e.g. GitHub Actions `::error file=...::`)
        # without having to re-read manifest.json.
        result = {
            "status": status,
            "run_id": run_id,
            "category": category,
            "baseline_solver_id": baseline_id,
            "axes": axes,
            "regression_case_ids": reg_ids,
            "pinned_baseline": pin_summary,
            "failures": failures,
            "warnings": warnings,
        }
        typer.echo(json.dumps(result, indent=2))
        if status == "fail":
            raise typer.Exit(1)
        return

    if failures:
        typer.echo("REGRESSION GATE FAILED:", err=True)
        for f in failures:
            typer.echo(f" - {f}", err=True)
        raise typer.Exit(1)
    if warnings:
        typer.echo("regression gate: WARN")
        for w in warnings:
            typer.echo(f" ! {w}")
        return
    typer.echo("regression gate passed")


@app.command("pin-baseline")
def pin_baseline(
    category: str = typer.Option("benchmark", help="Report category subtree."),
) -> None:
    """Pin the latest run's geomean speedup as the self-vs-self perf baseline.

    The pin is consumed by ``gate`` to answer "did *we* get slower this week?"
    independently of the lmfit-relative speedup. Overwrites any prior pin.
    """
    path = latest_results(category)
    if path is None:
        typer.echo(
            f"pin-baseline: no results under {REPORTS_ROOT / category}", err=True
        )
        raise typer.Exit(2)
    manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
    pinned_path = write_perf_baseline(manifest)
    geomean = _gate_geomean(manifest)
    baseline_id = manifest.get("baseline_solver_id", "lmfit")
    typer.echo(
        f"pinned {manifest['run_id']} ({geomean:.2f}x vs {baseline_id}) → {pinned_path}"
    )


@app.command("show-baseline")
def show_baseline() -> None:
    """Print the pinned perf baseline as JSON, or ``no perf baseline pinned``."""
    pin = read_perf_baseline()
    if pin is None:
        typer.echo("no perf baseline pinned")
        return
    typer.echo(json.dumps(pin, indent=2))


@app.command("clear-baseline")
def clear_baseline() -> None:
    """Remove the pinned perf baseline so the self-vs-self gate stops firing."""
    if clear_perf_baseline():
        typer.echo("perf baseline cleared")
    else:
        typer.echo("no perf baseline pinned")


def _fmt_speedup(value: float) -> str:
    """Format a speedup multiplier as ``12.5×`` (one decimal, U+00D7 multiplier sign).

    Hand-rolled because ``oracles.metrics`` has no formatter helper; mirrors
    the web-side ``fmtSpeedup`` precision so the prose paragraph matches what
    the UI shows.
    """
    return f"{value:.1f}×"


def _fmt_dr2(value: float) -> str:
    """Format max |Δr²| in scientific notation (``1.3e-04``)."""
    return f"{value:.1e}"


def _fmt_win_rate(value: float) -> str:
    """Format the spectrafit composite-score win rate as ``88.5%`` (one decimal)."""
    return f"{value * 100:.1f}%"


def _narrate_from_manifest(manifest: dict) -> str:
    """Render a release-notes Markdown paragraph from a manifest dict.

    Pulled out of the Typer command so the test can drive the formatter
    directly without touching the filesystem and so the command itself is just
    glue (read manifest → call this → echo).

    All field reads use ``.get`` with safe defaults so a forward-compat
    manifest (extra fields) or a slightly older one (missing optional field)
    never crashes the narration — releases must still get described even if
    the schema added something new.
    """
    baseline = manifest.get("baseline_solver_id", "lmfit")
    # Canonical key first, then the one-cycle legacy alias, then a neutral 1.0
    # fallback (same convention as ``_gate_geomean``).
    geomean = float(
        manifest.get(
            "geomean_speedup_vs_baseline",
            manifest.get("geomean_speedup_vs_lmfit", 1.0),
        )
    )
    dr2 = float(manifest.get("max_abs_delta_r2", 0.0))
    win_rate = float(manifest.get("spectrafit_win_rate", 0.0))
    n_cases = int(manifest.get("n_cases", 0))
    run_id = str(manifest.get("run_id", "unknown"))
    reg_ids = list(manifest.get("regression_case_ids") or [])

    # Regressions clause: zero is worth saying ("no regressions"), and the id
    # list is short enough on a healthy run that we can spell every one out
    # rather than truncating — the paragraph is for release notes, not logs.
    match len(reg_ids):
        case 0:
            regressions_clause = "No regressions."
        case 1:
            regressions_clause = f"One regression: {reg_ids[0]}."
        case n:
            regressions_clause = f"{n} regressions: {', '.join(reg_ids)}."

    return (
        f"SpectraFit improves peak-fitting speed by {_fmt_speedup(geomean)} geomean "
        f"vs {baseline} on the {n_cases}-case benchmark suite (run {run_id}). "
        f"Accuracy is maintained: max |Δr²| {_fmt_dr2(dr2)} across the LM-family "
        f"categories (optfn excluded by design). spectrafit wins "
        f"{_fmt_win_rate(win_rate)} of cases by composite r²·speedup. "
        f"{regressions_clause}"
    )


@app.command()
def narrate(
    run: str | None = typer.Option(
        None,
        "--run",
        help="Specific run id to narrate (default: latest run for the category).",
    ),
    category: str = typer.Option("benchmark", help="Report category subtree."),
) -> None:
    """Print a Markdown release-notes paragraph for a benchmark run.

    Reads ``manifest.json`` from the requested run (or the latest run if
    ``--run`` is omitted) and emits a single deterministic paragraph suitable
    for pasting into ``CHANGELOG.md`` or a release announcement. Errors
    cleanly (exit 2, no traceback) if no run is available so a fresh checkout
    or a wiped reports tree does not surface as a crash.
    """
    if run is None:
        # Pass ``root=`` explicitly so tests that monkeypatch
        # ``oracles.reports.REPORTS_ROOT`` (or the alias re-exported into
        # this module) override the search location; ``latest_run_dir``'s
        # default arg captures the module-level value at def-time.
        run_dir = latest_run_dir(category, root=REPORTS_ROOT)
        if run_dir is None:
            typer.echo(f"narrate: no runs under {REPORTS_ROOT / category}", err=True)
            raise typer.Exit(2)
    else:
        run_dir = REPORTS_ROOT / category / run
        if not run_dir.is_dir():
            typer.echo(f"narrate: run not found: {run_dir}", err=True)
            raise typer.Exit(2)

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        typer.echo(
            f"narrate: {manifest_path} missing — run may have failed mid-write",
            err=True,
        )
        raise typer.Exit(2)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    typer.echo(_narrate_from_manifest(manifest))


@app.command()
def forensics(
    run: str | None = typer.Option(None, "--run", help="Run id; default: latest."),
    category: str = typer.Option("benchmark", help="Report category."),
) -> None:
    """Render matplotlib PNGs for the regressed cases of a benchmark run.

    Useful triage path when `spc-bench gate` fails: the PNGs land at
    `.spectrafit_reports/<run>/forensics/<case_id>.png` so the user can
    eyeball what's broken.
    """
    if run is None:
        run_dir = latest_run_dir(category, root=REPORTS_ROOT)
        if run_dir is None:
            typer.echo(f"forensics: no runs under {REPORTS_ROOT / category}", err=True)
            raise typer.Exit(2)
    else:
        run_dir = REPORTS_ROOT / category / run
        if not run_dir.is_dir():
            typer.echo(f"forensics: run not found: {run_dir}", err=True)
            raise typer.Exit(2)

    from oracles.backends import get_backends

    paths = render_regressions(run_dir, backends=get_backends())
    if paths:
        typer.echo(f"rendered {len(paths)} PNG(s) → {run_dir / 'forensics'}")
    else:
        typer.echo(f"no regressions in run {run_dir.name} — nothing to render")


# ---------------------------------------------------------------------------
# spc-bench trend — per-axis history viewer (Cycle 13)
# ---------------------------------------------------------------------------

# Canonical field set tracked by `trend`. Keys match `manifest.json`; labels are
# user-facing column headers. The four axes match `spc-bench gate`, so a
# green-then-red trend in any column reads the same as the gate failing — just
# with history attached.
_TREND_FIELDS: dict[str, tuple[str, str]] = {
    "geomean_speedup_vs_baseline": ("geomean", "{:.2f}×"),
    "max_abs_delta_r2": ("max |Δr²|", "{:.2e}"),
    "regressions": ("regressions", "{:d}"),
    "spectrafit_win_rate": ("win-rate", "{:.0%}"),
    # Verification health over time (written onto the index entry by run_audit).
    # Older runs predate these keys → trend renders "—" for them.
    "rung": ("rung", "{:.0f}/5"),
    "wires_pass": ("wires", "{:.0f}"),
}


def _sparkline(values: list[float], width: int = 10) -> str:
    """ASCII sparkline of *values* using Unicode block characters.

    Empty / single-value series collapse to an empty string so the caller's
    column layout doesn't drift; width-limited to the last `width` points.
    """
    blocks = "▁▂▃▄▅▆▇█"
    vs = [float(v) for v in values[-width:] if v is not None]
    if len(vs) < 2:
        return ""
    lo, hi = min(vs), max(vs)
    span = hi - lo
    if span <= 0:
        return blocks[3] * len(vs)
    return "".join(blocks[min(7, int((v - lo) / span * 7.999))] for v in vs)


@app.command()
def trend(
    field: str = typer.Option(
        "all",
        "--field",
        help="Manifest key to track; `all` shows every gate axis.",
    ),
    category: str = typer.Option("benchmark", help="Report category subtree."),
    last: int = typer.Option(10, "--last", help="How many recent runs to show."),
) -> None:
    """Print the history of one or more manifest fields across runs.

    Reads ``.spectrafit_reports/index.json`` and emits a compact table with one
    row per run and one column per tracked field. An ASCII sparkline summarises
    each axis at the top so a regression is visible in 3 lines, not 30. Use
    after a series of changes to answer "did *we* get slower this week?" — the
    per-run history the self-vs-self pin can only answer for one snapshot at
    a time.
    """
    fields_to_show = list(_TREND_FIELDS) if field == "all" else [field]
    unknown = [f for f in fields_to_show if f not in _TREND_FIELDS]
    if unknown:
        typer.echo(
            f"trend: unknown field(s) {unknown}; valid: {list(_TREND_FIELDS)}",
            err=True,
        )
        raise typer.Exit(2)

    index_path = REPORTS_ROOT / "index.json"
    if not index_path.exists():
        typer.echo(f"trend: no index.json under {REPORTS_ROOT}", err=True)
        raise typer.Exit(2)
    runs = json.loads(index_path.read_text(encoding="utf-8"))
    runs = [r for r in runs if r.get("category") == category][:last]
    if not runs:
        typer.echo(f"trend: no runs in category {category!r}", err=True)
        raise typer.Exit(2)

    # Oldest → newest for the sparkline so time reads left-to-right.
    runs_chrono = list(reversed(runs))
    columns: dict[str, list[float | int]] = {}
    for key in fields_to_show:
        columns[key] = [
            int(r.get(key, 0) or 0)
            if key == "regressions"
            else float(r.get(key, 0.0) or 0.0)
            for r in runs_chrono
        ]

    # Sparkline header per field.
    for key in fields_to_show:
        label, fmt = _TREND_FIELDS[key]
        spark = _sparkline([float(v) for v in columns[key]])
        last_val = columns[key][-1] if columns[key] else 0
        typer.echo(f"  {label:>11s}  {spark:<10s}  last: {fmt.format(last_val)}")
    typer.echo("")

    # Table — newest first; matches the operator's "what's the latest?" expectation.
    header = f"  {'run_id':<24s}  " + "  ".join(
        f"{_TREND_FIELDS[k][0]:>11s}" for k in fields_to_show
    )
    typer.echo(header)
    typer.echo("  " + "-" * (len(header) - 2))
    for r in runs:
        cells = []
        for k in fields_to_show:
            v = r.get(k)
            if v is None:
                cells.append(f"{'—':>11s}")
            elif k == "regressions":
                cells.append(f"{int(v):>11d}")
            else:
                _, fmt = _TREND_FIELDS[k]
                cells.append(f"{fmt.format(float(v)):>11s}")
        typer.echo(f"  {r['run_id']:<24s}  " + "  ".join(cells))


@app.command()
def sweep(
    tiers: str = typer.Option(
        "1,2,5,10",
        "--tiers",
        help=(
            "Comma-separated `--reps` budgets to run sequentially. Higher tiers "
            "stabilise timing noise but multiply wall-clock; 1,2,5,10 takes ~3-4× "
            "longer than a single normal run."
        ),
    ),
    mc: int = typer.Option(
        4,
        "--mc",
        help=(
            "Monte-Carlo realisations per tier. Kept fixed at 4 by default so "
            "the sweep isolates `--reps` as the only varying knob; bump if you "
            "want per-tier accuracy stability too."
        ),
    ),
    category: str = typer.Option(
        "sweep", help="Subcategory under .spectrafit_reports/ (default: sweep)."
    ),
) -> None:
    """Run the bench at multiple `--reps` budgets; emit a budget-vs-signal table.

    Answers the verification-loop question "how many reps do I actually need
    before the gate signal is stable?" — cheap tiers (1, 2) often disagree
    with expensive tiers (10, 25) on geomean and regression count because
    timing noise pollutes the median; the sweep makes that disagreement
    visible in one pass instead of three separate runs the operator has to
    correlate by run_id.

    Each tier writes a normal results.json + manifest.json into
    `.spectrafit_reports/<category>/<date>_run_NNN`; the table at the end
    summarises the four gate axes per tier so a regression at one budget
    that disappears at another stands out.
    """
    try:
        tier_list = [int(t.strip()) for t in tiers.split(",") if t.strip()]
    except ValueError as exc:
        typer.echo(
            f"sweep: invalid --tiers ({exc}); expected comma-separated ints", err=True
        )
        raise typer.Exit(2) from exc
    if not tier_list:
        typer.echo("sweep: --tiers must contain at least one integer", err=True)
        raise typer.Exit(2)
    if any(t <= 0 for t in tier_list):
        typer.echo("sweep: every tier must be > 0", err=True)
        raise typer.Exit(2)

    # Tier-by-tier orchestration. We reuse `build_report` + `write_run` so each
    # tier lands as a full, gate-able run — the same shape any other `spc-bench
    # run` produces. Sweep adds no new contract; it's just an orchestrator.
    rows: list[dict] = []
    for tier in tier_list:
        typer.echo(f"sweep: running tier reps={tier} mc={mc} → category={category!r}…")
        report = build_report(n_reps=tier, n_mc=mc)
        run_dir = write_run(report, category=category)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        rows.append(
            {
                "tier": tier,
                "run_id": run_dir.name,
                "geomean": _gate_geomean(manifest),
                "max_dr2": float(manifest.get("max_abs_delta_r2", 0.0)),
                "regressions": int(manifest.get("regressions", 0) or 0),
                "win_rate": float(manifest.get("spectrafit_win_rate", 0.0)),
            }
        )

    # Summary table at the end. The right way to read this: scan the
    # `regressions` column for swings (1→0→1 with budget suggests timing
    # noise, not real signal) and the `geomean` column for convergence
    # (high-tier geomean is the honest number).
    typer.echo("")
    typer.echo(
        f"  {'tier':>6s}  {'run_id':<24s}  {'geomean':>10s}  {'max|Δr²|':>10s}  {'regressions':>11s}  {'win-rate':>9s}"
    )
    typer.echo("  " + "-" * 80)
    for r in rows:
        typer.echo(
            f"  {r['tier']:>6d}  {r['run_id']:<24s}  "
            f"{r['geomean']:>9.2f}×  {r['max_dr2']:>10.2e}  "
            f"{r['regressions']:>11d}  {r['win_rate']:>8.0%}"
        )


@app.command()
def stability(
    ladder_dir: Path = typer.Argument(
        ...,
        help=(
            "Directory containing reps-N subdirectories (reps-1/, reps-2/, …), "
            "each holding a contract-valid results.json — the layout the "
            "benchmark:deep CI matrix stages under artifacts/deep/."
        ),
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory for stability.json + stability.md.",
    ),
) -> None:
    """Aggregate a reps-ladder of runs into variance-vs-N stability artifacts.

    Loads every ``reps-N/results.json`` (validated against the ``BenchReport``
    contract), extracts per-backend suite headline numbers (geomean speedup,
    median speedup, median per-case ms) per reps budget, and writes:

    - ``stability.json`` — the typed :class:`oracles.stability.StabilityStudy`
      payload (a CI artifact schema, NOT the frozen wire contract);
    - ``stability.md`` — a reps × backend table of geomean speedups with signed
      Δ% vs the highest-reps reference, plus a converged-at-N verdict.

    Consumed by the ``benchmark:deep:merge`` GitLab job; the highest-reps run
    (N=100 in CI) is the canonical publication run for the paper.
    """
    if not ladder_dir.is_dir():
        typer.echo(f"stability: not a directory: {ladder_dir}", err=True)
        raise typer.Exit(2)
    study = build_stability_study(ladder_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "stability.json"
    md_path = out / "stability.md"
    json_path.write_text(study.model_dump_json(indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(study), encoding="utf-8")
    typer.echo(
        f"stability study over reps ladder {study.reps_ladder} → "
        f"{json_path} + {md_path}"
    )
    typer.echo(verdict_line(study))


def main(argv: list[str] | None = None) -> int:
    """Run the Typer app as a module entry point and return an exit code.

    With ``standalone_mode=False`` click does not re-raise ``typer.Exit``; instead it
    returns the requested exit code as the call's value, so a command's
    ``raise typer.Exit(2)`` surfaces here as a return value, not an exception.
    """
    try:
        rv = app(args=argv, standalone_mode=False)
    except SystemExit as exc:  # typer/click exits
        return int(exc.code or 0)
    except typer.Exit as exc:
        return int(exc.exit_code)
    # click returns the exit code (or None for a normal command return).
    return int(rv) if isinstance(rv, int) else 0


if __name__ == "__main__":
    sys.exit(main())
