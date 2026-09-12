r"""Reduce a benchmark run's artifacts to a small, figure-ready sidecar.

Why this exists: a full `results.json` is ~46 MB, almost all of it per-point
curve and residual arrays that no figure needs. Loading it repeatedly (once per
figure, once per check) is both slow and a genuine memory hazard — the repo's
own `guard-memory-hazards` pre-tool hook refuses reads of it for that reason.
This script performs exactly one heavy read and writes a few-kilobyte summary
that the figure scripts consume instead.

Usage:

    uv run --group manuscript python manuscript/examples/figures/extract_bench_summary.py \\
        <run-dir-or-results.json> [--trust <trust.json>] [--out <summary.json>]

`<run-dir>` may be a directory containing `results.json` / `manifest.json` /
`trust.json`, or the path to `results.json` directly. The NIST block is read
from `trust.json` when present — it is a separate, small sidecar that the
benchmark writes alongside the results.

What is kept, and why:

* per-case, per-solver median solve time and success flag — the only inputs a
  Dolan-More performance profile needs;
* per-case accuracy (r2) and the winner — for the win-rate and regression
  counts quoted in the text;
* the manifest's headline aggregates, copied verbatim rather than recomputed,
  so the paper and the gate cannot disagree about what the run said;
* the NIST per-dataset agreement in significant figures.

Everything else — curves, residuals, per-iteration histories, Monte-Carlo
ensembles — is dropped.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]

# NIST classifies each StRD nonlinear-regression dataset Lower / Average /
# Higher difficulty, and that is the axis a numerical-methods reviewer reads
# first: passing Lower-difficulty datasets is expected, passing Higher-difficulty
# ones is the actual correctness claim. The classification is recorded per
# dataset in this repo's own fixture modules, so it is read from there rather
# than hardcoded here — one source of truth, and a new dataset carries its tier
# with it.
_TIER_RE = re.compile(r'NIST classifies \S+ as \*\*"(\w+)"\*\*')


def nist_difficulty_tiers() -> dict[str, str]:
    """Map lowercased dataset name -> NIST difficulty tier, from the fixtures."""
    tiers: dict[str, str] = {}
    fixtures = REPO / "python" / "oracles" / "nist_strd"
    for path in sorted(fixtures.glob("*.py")):
        if path.stem == "__init__":
            continue
        m = _TIER_RE.search(path.read_text())
        if m:
            tiers[path.stem.lower()] = m.group(1)
    return tiers


def _local_nist_validation() -> dict[str, Any] | None:
    """Recompute the certified-value check from the fixtures at this commit.

    Returns ``None`` if the audit module is unavailable, so the caller falls back
    to whatever the run recorded.
    """
    try:
        from oracles.audit.nist import run_nist_validation
    except ImportError:
        return None
    v = run_nist_validation()
    return {
        "threshold_sig_figs": v.threshold_sig_figs,
        "total_available": v.total_available,
        "passed": v.passed,
        "min_sig_figs": v.min_sig_figs,
        "computed": "locally at this commit; accuracy is host-independent",
        "datasets": [d.model_dump() for d in v.datasets],
    }


def _load(path: Path) -> Any:
    """Read a JSON artifact, transparently handling a gzipped one.

    The benchmark ladder published under `manuscript/examples/ladder/` ships
    `results.json.gz` rather than `results.json`, because the uncompressed
    payload is large enough that the repo's `guard-memory-hazards` hook refuses
    to read it. A reader who downloads that package should be able to point
    this script straight at a rung directory, so both spellings are accepted.
    """
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, mode="rt", encoding="utf-8") as fh:
        return json.load(fh)


def _resolve(directory: Path, stem: str) -> Path | None:
    """Find `<stem>` or `<stem>.gz` inside a run directory."""
    for candidate in (directory / stem, directory / f"{stem}.gz"):
        if candidate.exists():
            return candidate
    return None


def summarise(results: dict, manifest: dict | None, trust: dict | None) -> dict:
    """Collapse a run into the fields the figures and the manuscript quote."""
    solvers = [s["id"] for s in results.get("solvers", [])]
    baseline = results.get("baselineSolverId") or results.get("baseline_solver_id")

    cases = []
    for case in results.get("suite", []):
        metrics = {}
        for solver_id, m in case.get("m", {}).items():
            metrics[solver_id] = {
                "med_ms": m.get("medMs", m.get("med_ms")),
                "r2": m.get("r2"),
                "speedup": m.get("speedup"),
                "success": m.get("success"),
                "ill_conditioned": m.get("illConditioned", m.get("ill_conditioned")),
                # param_err and red_chi2 were dropped by an earlier version of
                # this extractor, which kept only timing plus r2. That discarded
                # the one axis the manuscript argues actually matters: r2 is
                # degenerate across backends here (median cross-backend spread
                # 1.1e-14, all six on the same optimum for 143 of 151 cases),
                # while param_err -- max relative shape-parameter error against
                # planted truth -- separates them on 124 of the 127 cases every
                # backend ran. A figure of parameter agreement cannot be drawn
                # from a summary that threw parameter agreement away.
                "param_err": m.get("paramErr", m.get("param_err")),
                "red_chi2": m.get("redChi2", m.get("red_chi2")),
            }
        cases.append(
            {
                "id": case.get("id"),
                "category": case.get("category"),
                "difficulty": case.get("difficulty"),
                "winner": case.get("winner"),
                "regression": case.get("regression"),
                "m": metrics,
            },
        )

    # A backend declared in the roster but with NO per-case entries did not run
    # at all — it is not a backend that failed every case. Conflating the two is
    # a real misreading: this run's CI environment installs the `benchmark`
    # extra but not the optional `jax` extra, so JAX was never exercised, and
    # plotting it as "0/151 solved" would assert a failure that never happened.
    # Per-solver ELIGIBILITY, which is not the same as success. A backend has
    # an entry only for cases it was actually asked to run, so three states must
    # be told apart:
    #   full-suite   — eligible for every case; failures are real failures
    #   partial      — structurally inapplicable to some cases (jax/optimistix
    #                  cannot express expression edges, so tied-parameter cases
    #                  are never offered to it)
    #   not run      — no entries at all; absent from the environment
    # Only full-suite backends belong on a performance profile: the profile's
    # y-axis is a fraction of the WHOLE suite, so a partial backend's curve
    # asymptotes at its eligibility by construction and reads as poor
    # robustness when it is nothing of the kind.
    eligible = {s: sum(1 for c in cases if s in c["m"]) for s in solvers}
    n = len(cases)
    out: dict[str, Any] = {
        "solvers": solvers,
        "solvers_eligible": eligible,
        "solvers_full_suite": sorted(s for s in solvers if eligible[s] == n and n),
        "solvers_partial": sorted(s for s in solvers if 0 < eligible[s] < n),
        "solvers_not_run": sorted(s for s in solvers if eligible[s] == 0),
        "baseline_solver_id": baseline,
        "n_cases": len(cases),
        "categories": [
            {"id": c.get("id"), "label": c.get("label"), "n": c.get("n")}
            for c in results.get("categories", [])
        ],
        "git_commit": results.get("gitCommit", results.get("git_commit")),
        "git_branch": results.get("gitBranch", results.get("git_branch")),
        "cases": cases,
    }

    if manifest:
        # Copied verbatim, never recomputed: the gate and the paper must not be
        # able to disagree about what this run reported.
        out["manifest"] = {
            k: manifest.get(k)
            for k in (
                "run_id",
                "date",
                "n_cases",
                "backends",
                "baseline_solver_id",
                "geomean_speedup_vs_baseline",
                "harmonic_mean_speedup_vs_baseline",
                "max_abs_delta_r2",
                "spectrafit_win_rate",
                "regressions",
                "regression_case_ids",
                "gate_state",
                "saturated_categories",
            )
            if k in manifest
        }

    if trust:
        tiers = nist_difficulty_tiers()
        block = trust.get("block", trust)
        # The certified-value check is recomputed here rather than copied out of
        # the run's trust.json. It is an ACCURACY result: deterministic, machine
        # independent, and a pure function of the fixtures and the solver at this
        # commit -- unlike the timings beside it, which are properties of the host
        # that produced the run. Copying it would pin the figure to whichever
        # fixture set existed when that run executed, so adding a dataset would
        # silently not appear. Falls back to the recorded block if the local
        # validation cannot run.
        nist = _local_nist_validation() or block.get("nist_validation")
        if nist:
            out["nist"] = {
                "threshold_sig_figs": nist.get("threshold_sig_figs"),
                "total_available": nist.get("total_available"),
                "passed": nist.get("passed"),
                "min_sig_figs": nist.get("min_sig_figs"),
                "computed": nist.get("computed", "copied from the run's trust.json"),
                "datasets": [
                    {
                        "name": d["name"],
                        "difficulty": tiers.get(d["name"].lower(), "unknown"),
                        "n_params": d.get("n_params"),
                        "min_sig_figs": d.get("min_sig_figs"),
                        "passed": d.get("passed"),
                        "params": [
                            {"name": p["name"], "sig_figs_agreed": p.get("sig_figs_agreed")}
                            for p in d.get("params", [])
                        ],
                    }
                    for d in nist.get("datasets", [])
                ],
            }
        out["trust_rung"] = block.get("rung")
        out["claims"] = {
            "audited": block.get("n_claims_audited"),
            "total": block.get("n_claims_total"),
        }

    return out


def main() -> None:
    """Read one run's artifacts and write the figure-ready summary."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run", type=Path, help="run directory, or results.json")
    ap.add_argument("--trust", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if args.run.is_dir():
        results_path = _resolve(args.run, "results.json") or (args.run / "results.json")
        manifest_path = _resolve(args.run, "manifest.json") or (args.run / "manifest.json")
        trust_path = args.trust or _resolve(args.run, "trust.json") or (args.run / "trust.json")
    else:
        results_path = args.run
        manifest_path = results_path.with_name("manifest.json")
        trust_path = args.trust or results_path.with_name("trust.json")

    results = _load(results_path)
    manifest = _load(manifest_path) if manifest_path.exists() else None
    trust = _load(trust_path) if trust_path.exists() else None
    if trust is None:
        print(f"note: no trust.json beside {results_path} — NIST block omitted")

    summary = summarise(results, manifest, trust)
    out = args.out or Path(__file__).resolve().parent / "bench_summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")

    size_in = results_path.stat().st_size / 1e6
    size_out = out.stat().st_size / 1e3
    print(
        f"{results_path.name} ({size_in:.1f} MB) -> {out.name} ({size_out:.0f} kB): "
        f"{summary['n_cases']} cases, {len(summary['solvers'])} solvers",
    )
    if "manifest" in summary:
        m = summary["manifest"]
        print(
            f"  run {m.get('run_id')}  geomean {m.get('geomean_speedup_vs_baseline')}  "
            f"regressions {m.get('regressions')}  gate {m.get('gate_state')}",
        )


if __name__ == "__main__":
    main()
