#!/usr/bin/env python3
r"""Fe L2,3 EELS constrained model: one graph JSON file fitted by SpectraFit-Core and by lmfit (#93).

The model is ``fe_l23_constrained.graph.json``: a constant background, one arctangent step
per spin-orbit edge and nine Gaussian white lines on the Fe L2,3 edge of Fe2O3 between 700
and 735 eV, with four expression edges (the L2 step is half the L3 step, both steps share
one width, each step sits at the centre of its main white line). SpectraFit-Core reads the
file with ``FitGraph.model_validate_json``; lmfit reads it through ``graph_to_lmfit.py``,
which never imports SpectraFit-Core. Both fits start from the file's values, keep its bounds
and fit the same data:

* SpectraFit-Core: ``fit(graph, data, FitOptions(solver="lm"))``;
* lmfit: ``Model.fit(y, params, x=x, method="leastsq")``.

Each fit reports RSS, every parameter with its standard error, termination, and
stationarity by the measure of the EELS solver cross-check (Gauss-Newton predicted decrease
divided by RSS at the endpoint, central-difference Jacobian over the free parameters with
$h = 6.06 \cdot 10^{-6} \max(|\theta|, 10^{-3})$, outward-pointing gradients of parameters
at an active bound held, stationary when $\le 10^{-6}$). Both endpoints are measured with
one model function, ``spectrafit_core.evaluate`` with the ties applied, and the lmfit model
is checked against it at both endpoints.

There are no random draws: one fixed start. The run header records versions, inputs and
their SHA-256.

    uv run python reproducibility/interop/fe_l23_lmfit.py --out DIR
    uv run python reproducibility/interop/fe_l23_lmfit.py --bundle B --write-graph   # regenerate the graph

``--bundle`` names a directory holding the cross-check's ``fig_eels.py``; the graph built
there (``graph("constrained")``: default start, default bounds) must equal the committed
file, and ``--write-graph`` rewrites the file from it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import importlib.util
import json
import os
import platform
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from itertools import zip_longest
from pathlib import Path
from typing import Any

import numpy as np
from spectrafit_core import FitGraph, FitOptions, MeasurementData, evaluate, fit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def _load_translator():
    """Import ``graph_to_lmfit.py`` from this folder (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location("graph_to_lmfit", HERE / "graph_to_lmfit.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["graph_to_lmfit"] = module
    spec.loader.exec_module(module)
    return module


g2l = _load_translator()

GRAPH = HERE / "fe_l23_constrained.graph.json"
SPECTRUM = ROOT / "reproducibility" / "spectra" / "eelsdb-fe2o3-l23" / "DspecTi3wqG.msa"
SPECTRUM_SHA256 = "28e88f85350c353f524c828740c533312dc897505410ac940cd544060df963d4"
FIG_EELS_SHA256 = "76f46afe1a138dbd3ab09124eb0db338b083e4f98c6b79ac448b4549172a0d09"
WINDOW_EV = (700.0, 735.0)

# The stationarity measure of the EELS solver cross-check (crosscheck.py, preregistered).
AT_BOUND_REL = 1e-4
H_REL, THETA_FLOOR = 6.06e-6, 1e-3
GN_TOL = 1e-6
EQUIV_TOL = 1e-10  # lmfit model vs spectrafit_core.evaluate, relative to max |f|
THREAD_CAPS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "RAYON_NUM_THREADS")


def sha256(path: Path) -> str:
    """Return the SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_msa(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read an EMSA ``#DATATYPE XY`` file (comma-separated ``x, y`` rows)."""
    x, y = [], []
    for line in path.read_text(encoding="latin-1").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        left, _, right = line.partition(",")
        x.append(float(left))
        y.append(float(right))
    return np.asarray(x), np.asarray(y)


class Problem:
    """Data, graph and the one model function both endpoints are measured with."""

    def __init__(self, graph_path: Path, spectrum: Path) -> None:
        """Read the spectrum window and the graph file, and translate the graph."""
        x, y = read_msa(spectrum)
        keep = (x >= WINDOW_EV[0]) & (x <= WINDOW_EV[1])
        self.x, self.y = x[keep], y[keep]
        self.data = MeasurementData(x=self.x.tolist(), y=self.y.tolist())
        self.raw = json.loads(graph_path.read_text(encoding="utf-8"))
        self.graph = FitGraph.model_validate_json(graph_path.read_text(encoding="utf-8"))
        self.translation = g2l.translate_file(graph_path)
        names = self.translation.names
        tied = {k for k, n in names.items() if self.translation.params[n].expr is not None}
        self.keys = list(names)
        self.free = [
            k for k in self.keys if k not in tied and self.translation.params[names[k]].vary
        ]
        spec = {f"{n['id']}.{p}": s for n in self.raw["nodes"] for p, s in n["parameters"].items()}
        self.start = {k: float(spec[k]["value"]) for k in self.keys}
        self.lo = {k: -np.inf if spec[k].get("min") is None else spec[k]["min"] for k in self.keys}
        self.hi = {k: np.inf if spec[k].get("max") is None else spec[k]["max"] for k in self.keys}
        # A copy of the lmfit parameters without bounds on the free ones: ties are applied
        # by lmfit's expression evaluation, and finite-difference steps are not clipped.
        self._tie_params = self.translation.params.copy()
        for k in self.free:
            self._tie_params[names[k]].set(min=-np.inf, max=np.inf)

    def full(self, free_values: dict[str, float]) -> dict[str, float]:
        """Return every parameter, with the ties applied, for given free values."""
        names = self.translation.names
        for k, v in free_values.items():
            self._tie_params[names[k]].set(value=float(v))
        values = self._tie_params.valuesdict()
        return {k: float(values[names[k]]) for k in self.keys}

    def model(self, p: dict[str, float]) -> np.ndarray:
        """Return ``spectrafit_core.evaluate`` at a full parameter set."""
        return np.asarray(evaluate(self.graph, p, self.data), dtype=float)

    def active(self, p: dict[str, float]) -> dict[str, str]:
        """Free parameters at an active bound, by the cross-check rule."""
        out = {}
        for k in self.free:
            lo, hi = self.lo[k], self.hi[k]
            two = np.isfinite(lo) and np.isfinite(hi)
            tol = AT_BOUND_REL * ((hi - lo) if two else max(abs(self.start[k]), 1.0))
            if p[k] - lo <= tol:
                out[k] = "lower"
            elif hi - p[k] <= tol:
                out[k] = "upper"
        return out

    def stationarity(self, p: dict[str, float]) -> dict[str, Any]:
        """Gauss-Newton predicted decrease / RSS at an endpoint (cross-check measure)."""
        active = self.active(p)
        theta = np.array([p[k] for k in self.free])
        scale = np.maximum(np.abs(theta), THETA_FLOOR)
        h = H_REL * scale
        r = self.y - self.model(p)
        rss = float(r @ r)
        jac = np.empty((self.y.size, theta.size))
        base = dict(zip(self.free, theta, strict=True))
        for i, k in enumerate(self.free):
            up = self.model(self.full({**base, k: theta[i] + h[i]}))
            dn = self.model(self.full({**base, k: theta[i] - h[i]}))
            jac[:, i] = (up - dn) / (2.0 * h[i])
        self.full(base)
        g = -2.0 * jac.T @ r
        held = np.array(
            [
                (active.get(k) == "lower" and g[i] > 0) or (active.get(k) == "upper" and g[i] < 0)
                for i, k in enumerate(self.free)
            ],
            dtype=bool,
        )
        pg = np.where(held, 0.0, g)
        js = jac[:, ~held] * scale[~held]
        step, *_ = np.linalg.lstsq(js, r, rcond=None)
        gn = float(np.sum((js @ step) ** 2) / rss)
        return {
            "gn_decrease_rel": gn,
            "stationary": gn <= GN_TOL,
            "pg_norm_rel": float(np.linalg.norm(pg) / rss),
            "pg_scaled_max_rel": float(np.max(np.abs(pg) * scale) / rss) if pg.size else 0.0,
            "active": active,
            "held": [k for k, hd in zip(self.free, held, strict=True) if hd],
        }

    def endpoint(self, reported: dict[str, float]) -> dict[str, Any]:
        """RSS, lmfit-vs-engine model gap and stationarity at a backend's endpoint.

        The tied parameters are recomputed from the free ones, so both endpoints are
        measured with the same tie evaluation; the largest difference to the backend's
        reported tied values is recorded.
        """
        p = self.full({k: reported[k] for k in self.free})
        tie_gap = max(
            (abs(p[k] - reported[k]) / max(abs(p[k]), THETA_FLOOR) for k in self.keys),
            default=0.0,
        )
        f = self.model(p)
        names = self.translation.names
        lm = self.translation.params.copy()
        for k in self.free:
            lm[names[k]].set(value=p[k], min=-np.inf, max=np.inf)
        f_lmfit = self.translation.model.eval(lm, x=self.x)
        gap = float(np.max(np.abs(f_lmfit - f)) / np.max(np.abs(f)))
        return {
            "rss": float(np.sum((self.y - f) ** 2)),
            "tied_values_gap_rel": tie_gap,
            "model_gap_lmfit_vs_engine": gap,
            "model_gap_ok": gap <= EQUIV_TOL,
            "stationarity": self.stationarity(p),
        }


def run_sfc(prob: Problem) -> dict[str, Any]:
    """Fit the graph with SpectraFit-Core."""
    t = time.perf_counter()
    r = fit(prob.graph, prob.data, FitOptions(solver="lm"))
    wall = time.perf_counter() - t
    p = {k: float(r.parameters[k].value) for k in prob.keys}
    return {
        "backend": "spectrafit-core fit, FitOptions(solver='lm')",
        "wall_s": wall,
        "termination": {
            "success": bool(r.success),
            "message": r.message,
            "n_iter": r.n_iter,
            "nfev": r.n_func_evals,
            "njev": r.n_jac_evals,
        },
        "params": {
            k: {"value": p[k], "stderr": r.parameters[k].stderr, "free": k in prob.free}
            for k in prob.keys
        },
        **prob.endpoint(p),
    }


def run_lmfit(prob: Problem) -> dict[str, Any]:
    """Fit the translated graph with lmfit."""
    tr = prob.translation
    t = time.perf_counter()
    res = tr.model.fit(prob.y, tr.params, x=prob.x, method="leastsq")
    wall = time.perf_counter() - t
    p = {k: float(res.params[n].value) for k, n in tr.names.items()}
    return {
        "backend": "lmfit Model.fit(method='leastsq')",
        "wall_s": wall,
        "termination": {
            "success": bool(res.success),
            "message": res.message,
            "ier": getattr(res, "ier", None),
            "lmdif_message": getattr(res, "lmdif_message", None),
            "nfev": res.nfev,
            "errorbars": bool(res.errorbars),
            "rss_backend": float(res.chisqr),
        },
        "params": {
            k: {"value": p[k], "stderr": res.params[n].stderr, "free": k in prob.free}
            for k, n in tr.names.items()
        },
        **prob.endpoint(p),
    }


def check_bundle(bundle: Path, write: bool) -> str:
    """Rebuild the graph from the cross-check's ``fig_eels.py`` and compare or write it."""
    path = bundle / "fig_eels.py"
    digest = sha256(path)
    if digest != FIG_EELS_SHA256:
        msg = f"{path} sha256 {digest} is not the cross-check's {FIG_EELS_SHA256}"
        raise SystemExit(msg)
    spec = importlib.util.spec_from_file_location("fig_eels", path)
    assert spec is not None
    assert spec.loader is not None
    fe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fe)
    text = fe.graph("constrained").model_dump_json(indent=2) + "\n"
    if write:
        GRAPH.write_text(text, encoding="utf-8")
    elif json.loads(text) != json.loads(GRAPH.read_text(encoding="utf-8")):
        msg = f"{GRAPH.name} differs from fig_eels.graph('constrained') in {bundle}"
        raise SystemExit(msg)
    return digest


def side_by_side(left: list[str], right: list[str], titles: tuple[str, str]) -> str:
    """Two text columns, the left padded to its widest line."""
    width = max(len(s) for s in [*left, titles[0]])
    rows = [f"{titles[0]:<{width}} | {titles[1]}", f"{'-' * width}-+-{'-' * 40}"]
    rows += [f"{a:<{width}} | {b}" for a, b in zip_longest(left, right, fillvalue="")]
    return "\n".join(rows) + "\n"


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.10g}"


def fit_table(prob: Problem, sfc: dict, lm: dict) -> str:
    """Both fits side by side: summary rows, then every parameter."""
    rows = [
        ("RSS (engine evaluate)", _fmt(sfc["rss"]), _fmt(lm["rss"])),
        ("success", str(sfc["termination"]["success"]), str(lm["termination"]["success"])),
        ("message", sfc["termination"]["message"], lm["termination"]["message"]),
        ("evaluations", f"nfev {sfc['termination']['nfev']}", f"nfev {lm['termination']['nfev']}"),
        (
            "GN decrease / RSS",
            f"{sfc['stationarity']['gn_decrease_rel']:.3g}",
            f"{lm['stationarity']['gn_decrease_rel']:.3g}",
        ),
        (
            "stationary (<= 1e-6)",
            str(sfc["stationarity"]["stationary"]),
            str(lm["stationarity"]["stationary"]),
        ),
        (
            "active bounds",
            ", ".join(f"{k} {v}" for k, v in sfc["stationarity"]["active"].items()) or "-",
            ", ".join(f"{k} {v}" for k, v in lm["stationarity"]["active"].items()) or "-",
        ),
        (
            "lmfit model vs engine",
            f"{sfc['model_gap_lmfit_vs_engine']:.2g}",
            f"{lm['model_gap_lmfit_vs_engine']:.2g}",
        ),
        ("", "", ""),
        ("parameter", "SpectraFit-Core value +- stderr", "lmfit value +- stderr"),
    ]
    for k in prob.keys:
        a, b = sfc["params"][k], lm["params"][k]
        tag = "" if k in prob.free else " (tied/fixed)"
        rows.append(
            (
                k + tag,
                f"{_fmt(a['value'])} +- {_fmt(a['stderr'])}",
                f"{_fmt(b['value'])} +- {_fmt(b['stderr'])}",
            ),
        )
    w0 = max(len(r[0]) for r in rows)
    w1 = max(len(r[1]) for r in rows)
    return "\n".join(f"{r[0]:<{w0}}  {r[1]:<{w1}}  {r[2]}" for r in rows) + "\n"


def compare(prob: Problem, sfc: dict, lm: dict) -> dict[str, Any]:
    """Differences between the two endpoints."""
    rel = {
        k: abs(lm["params"][k]["value"] - sfc["params"][k]["value"])
        / max(abs(sfc["params"][k]["value"]), THETA_FLOOR)
        for k in prob.free
    }
    worst = max(rel, key=rel.get)
    return {
        "rss_lmfit_minus_sfc": lm["rss"] - sfc["rss"],
        "rss_rel_diff": (lm["rss"] - sfc["rss"]) / sfc["rss"],
        "param_rel_diff_max": rel[worst],
        "param_rel_diff_argmax": worst,
        "param_rel_diff": rel,
    }


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def main(argv: list[str] | None = None) -> int:
    """Run both fits, print the side-by-side output and write it to ``--out``."""
    ap = argparse.ArgumentParser(description="Fit one graph JSON with SpectraFit-Core and lmfit.")
    ap.add_argument("--spectrum", type=Path, default=SPECTRUM)
    ap.add_argument("--out", type=Path, default=None, help="directory for the JSON and text output")
    ap.add_argument("--bundle", type=Path, default=None, help="directory with fig_eels.py")
    ap.add_argument("--write-graph", action="store_true", help="rewrite the graph from --bundle")
    args = ap.parse_args(argv)

    fig_eels_sha = None
    if args.bundle is not None:
        fig_eels_sha = check_bundle(args.bundle, args.write_graph)
        if args.write_graph:
            print(f"wrote {GRAPH}")
            return 0
    if sha256(args.spectrum) != SPECTRUM_SHA256:
        msg = f"{args.spectrum}: sha256 does not match the EELS Data Base record"
        raise SystemExit(msg)

    started = datetime.now(UTC)
    prob = Problem(GRAPH, args.spectrum)
    sfc = run_sfc(prob)
    lm = run_lmfit(prob)
    lmfit_lines = prob.translation.source.splitlines()
    lmfit_lines += [f"# note: {n}" for n in prob.translation.notes]
    definitions = side_by_side(
        GRAPH.read_text(encoding="utf-8").splitlines(),
        lmfit_lines,
        (f"graph JSON ({GRAPH.name})", "lmfit code (graph_to_lmfit.py)"),
    )
    fits = fit_table(prob, sfc, lm)
    record = {
        "header": {
            "command": shlex.join([sys.executable, *sys.argv]),
            "cwd": str(Path.cwd()),
            "started_utc": started.isoformat(timespec="seconds"),
            "finished_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "git_commit": _git("rev-parse", "HEAD"),
            "git_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
            "versions": {p: md.version(p) for p in ("spectrafit-core", "lmfit", "scipy", "numpy")},
            "python": sys.version.split()[0],
            "host": f"{platform.node()} {platform.platform()} {platform.machine()}",
            "thread_caps": {k: os.environ.get(k) for k in THREAD_CAPS},
            "random_draws": "none (one fixed start: the graph file's values)",
            "inputs": {
                "spectrum": str(args.spectrum.relative_to(ROOT))
                if args.spectrum.is_relative_to(ROOT)
                else str(args.spectrum),
                "spectrum_sha256": sha256(args.spectrum),
                "graph": GRAPH.name,
                "graph_sha256": sha256(GRAPH),
                "translator_sha256": sha256(HERE / "graph_to_lmfit.py"),
                "fig_eels_sha256_checked": fig_eels_sha,
            },
            "window_ev": list(WINDOW_EV),
            "n_points": int(prob.y.size),
            "n_free": len(prob.free),
            "measure": {
                "AT_BOUND_REL": AT_BOUND_REL,
                "H_REL": H_REL,
                "THETA_FLOOR": THETA_FLOOR,
                "GN_TOL": GN_TOL,
                "EQUIV_TOL": EQUIV_TOL,
            },
        },
        "translation_notes": prob.translation.notes,
        "free": prob.free,
        "sfc": sfc,
        "lmfit": lm,
        "comparison": compare(prob, sfc, lm),
    }
    sys.stdout.write(definitions + "\n" + fits)
    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "fe_l23_lmfit.json").write_text(
            json.dumps(record, indent=1, default=float) + "\n",
            encoding="utf-8",
        )
        (args.out / "fe_l23_side_by_side.txt").write_text(
            definitions + "\n" + fits,
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
