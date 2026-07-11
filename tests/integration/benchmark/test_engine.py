"""Engine end-to-end: a tiny injected catalog produces a contract-valid report.

Keeps runtime small (a 3-case catalog, 1 rep, 2 MC, a 2-point scaling grid) while
exercising the full pipeline: suite + featured deep-dive → BenchReport → run-dir
write (results.json + manifest.json + index.json) → regression-gate headline.
"""

from __future__ import annotations

import json

from oracles.cases import build_specs, materialize
from oracles.bench_contract import BenchReport
from oracles.engine import build_report
from oracles.reports import latest_results, write_run


def _tiny_catalog() -> list:
    """Featured case + one easy + one complex, materialized."""
    specs = build_specs()
    featured = next(s for s in specs if s.featured)
    easy = next(s for s in specs if s.category == "easy")
    complx = next(s for s in specs if s.category == "complex")
    return [materialize(s) for s in (featured, easy, complx)]


def test_engine_builds_contract_valid_report() -> None:
    """build_report on a tiny catalog yields a valid, round-trippable BenchReport."""
    catalog = _tiny_catalog()
    report = build_report(n_reps=1, n_mc=2, catalog=catalog, ngrid=[128, 256])
    assert isinstance(report, BenchReport)
    assert len(report.suite) == 3
    # Subset assertion (relaxed for the scipy-ls extension, 2026-06-08): the
    # canonical 3 must always be present; additions are additive.
    assert {"spectrafit", "lmfit", "jax"}.issubset({s.id for s in report.solvers})

    # `analyzed` is a list of deep-dived cases (unique ids); this tiny catalog has no
    # `edge` cases, so it falls back to the single featured case.
    assert len(report.analyzed) >= 1
    assert len({f.id for f in report.analyzed}) == len(report.analyzed)
    f = report.analyzed[0]
    assert "spectrafit" in f.profiles
    sf = f.profiles["spectrafit"]
    assert sf.history_source == "real"
    assert len(sf.conv) >= 2
    assert len(sf.scaling) == 2
    assert len(sf.fit.params) == 3
    assert len(f.corr) == len(f.param_names)  # square correlation matrix
    # Decimation keeps plotted arrays aligned and bounded.
    assert len(f.x) == len(f.ref) == len(f.guess) == len(sf.fit.curve) <= 200

    # Round-trips through JSON unchanged (no lossy fields).
    raw = report.model_dump_json(by_alias=True)
    assert BenchReport.model_validate_json(raw).model_dump_json(by_alias=True) == raw


def test_only_spectrafit_subject_claims_real_history() -> None:
    """EF-PLOTS-09: oracle backends must NEVER tag their history as 'real'.

    The convergence panel splits 'real' (the subject's measured cost history)
    from 'reconstructed' (oracle proxy). Existing tests assert spectrafit IS
    real; this is the negative guard — lmfit / jax / scipy-ls (and any other
    non-subject backend) must report 'reconstructed'. A proxy mislabeled 'real'
    is the proxy-as-real hazard the render-truth split exists to prevent.
    """
    catalog = _tiny_catalog()
    report = build_report(n_reps=1, n_mc=2, catalog=catalog, ngrid=[128, 256])
    f = report.analyzed[0]
    real_backends = {
        sid for sid, prof in f.profiles.items() if prof.history_source == "real"
    }
    # The subject (spectrafit) is the ONLY backend allowed to claim real history.
    assert real_backends <= {"spectrafit"}, (
        f"oracle backend(s) {real_backends - {'spectrafit'}} claimed history_source"
        "=='real' — only the subject may carry a measured convergence history."
    )


def test_conv_eff_provenance_gated_on_real_history() -> None:
    """EF-PY-11: ``conv_eff`` is a measured series only for ``history_source=='real'``.

    ``conv_eff`` is derived from the convergence cost history ``conv``. For
    oracle backends that history is *reconstructed* (a proxy), so a conv_eff
    derived from it would be a proxy presented as a measured efficiency. Gate
    it: only the subject (spectrafit, real history) emits a populated conv_eff;
    reconstructed-history backends emit ``None`` so no consumer can mistake a
    proxy-derived series for a measured one.
    """
    catalog = _tiny_catalog()
    report = build_report(n_reps=1, n_mc=2, catalog=catalog, ngrid=[128, 256])
    f = report.analyzed[0]
    for solver_id, prof in f.profiles.items():
        if prof.history_source == "real":
            assert prof.conv_eff, (
                f"{solver_id}: real history must carry a populated conv_eff series"
            )
        else:
            assert prof.conv_eff is None, (
                f"{solver_id}: reconstructed history must not present conv_eff as "
                f"a measured series (got {prof.conv_eff!r})"
            )


def test_deep_dive_mixed_peak_background_is_graph_indexed() -> None:
    """A case with a NON-peak component before peaks deep-dives without raising, and
    truth / fit.params stay GRAPH-INDEXED (one entry per component).

    Regression for two coupled bugs: (1) ``KeyError: p{i}.sigma`` when a component
    lacks sigma (quadratic/fano/decay), and (2) the off-by-one wrong-peak attribution
    when truth/_peakacs were filtered to peak-only positions while the web ExportView
    still indexes ``truth[pi]`` by the dotted ``p{i}`` graph index.
    """
    from oracles.cases import CaseSpec, GaussianSpec, QuadraticSpec, materialize

    spec = CaseSpec(
        id="TST-001",
        name="quad bg + 2 gaussians",
        category="reality",
        difficulty=0.3,
        components=[
            QuadraticSpec(amplitude=0.02, center=0.0, offset=0.5),  # p0 — no sigma
            GaussianSpec(amplitude=3.0, center=-1.5, sigma=0.6),  # p1
            GaussianSpec(amplitude=2.0, center=1.8, sigma=0.5),  # p2
        ],
        x_min=-5.0,
        x_max=5.0,
        n_points=200,
        noise=0.02,
    )
    report = build_report(
        n_reps=1, n_mc=2, catalog=[materialize(spec)], ngrid=[128, 256]
    )
    f = report.analyzed[0]
    # Graph-indexed: one entry per component (3), NOT filtered to the 2 peaks.
    assert len(f.truth) == 3
    assert len(f.peaks) == 3  # peak-contribution curves share the same index space
    assert len(f.profiles["spectrafit"].fit.params) == 3  # graph-indexed too
    # The two gaussians sit at graph indices 1 and 2 with their true centers.
    assert f.truth[1].c == -1.5
    assert f.truth[2].c == 1.8
    # The quadratic background (index 0) has no sigma → 0.0 sentinel (never surfaced).
    assert f.truth[0].s == 0.0


def test_write_run_creates_run_tree(tmp_path) -> None:
    """write_run lays down results.json + manifest.json and updates index.json."""
    report = build_report(n_reps=1, n_mc=2, catalog=_tiny_catalog(), ngrid=[128, 256])
    run_dir = write_run(report, category="benchmark", root=tmp_path)

    assert (run_dir / "results.json").exists()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["n_cases"] == 3
    # Subset assertion (relaxed for the scipy-ls extension, 2026-06-08): the
    # canonical 3 must always be present and in their canonical order; later
    # additions append after them.
    assert manifest["backends"][:3] == ["spectrafit", "lmfit", "jax"]
    assert {"spectrafit", "lmfit", "jax"}.issubset(set(manifest["backends"]))
    assert manifest["geomean_speedup_vs_lmfit"] > 0
    # The manifest must carry the regression case-id list (even if empty) so the
    # CLI can summarize backend failures in one line — keeping the report_html
    # operator from `^C`'ing the run on what is just a few-case regression.
    assert "regression_case_ids" in manifest
    assert isinstance(manifest["regression_case_ids"], list)
    assert manifest["regressions"] == len(manifest["regression_case_ids"])

    index = json.loads((tmp_path / "index.json").read_text())
    assert index[0]["run_id"] == run_dir.name
    assert latest_results("benchmark", root=tmp_path) == run_dir / "results.json"


def test_manifest_lists_failing_case_ids_when_backend_regresses(tmp_path) -> None:
    """A suite with a forced-regression case surfaces it in manifest.regression_case_ids."""
    from oracles.bench_contract import BenchReport, CategoryMeta, SolverMeta, SuiteCase

    # Synthesize a tiny BenchReport with one failing case so the headline computation
    # is exercised end-to-end without needing a backend to actually fail at runtime.
    report = BenchReport(
        solvers=[
            SolverMeta(id="spectrafit", label="spectrafit", color="#fff", soft="#eee")
        ],
        categories=[CategoryMeta(id="easy", label="Easy", n=2, hue="#fff")],
        analyzed=[],
        suite=[
            SuiteCase(
                id="EZ-001",
                name="ok case",
                category="easy",
                difficulty=0.1,
                m={},
                winner="",
                regression=False,
            ),
            SuiteCase(
                id="EZ-002",
                name="failing case",
                category="easy",
                difficulty=0.1,
                m={},
                winner="",
                regression=True,
            ),
        ],
    )
    run_dir = write_run(report, category="benchmark", root=tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["regression_case_ids"] == ["EZ-002"]
    assert manifest["regressions"] == 1
