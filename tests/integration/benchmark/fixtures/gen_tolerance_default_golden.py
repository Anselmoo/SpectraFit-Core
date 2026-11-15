"""Generate the golden of the benchmark's default stopping-tolerance mode.

Runs every benchmark backend once on one case per category and writes the
deterministic part of each normalised outcome (floats as ``float.hex`` so the
comparison is bit for bit and NaN-safe). It uses only API that existed before the
tolerance modes were added (``get_backends()``, ``Backend.build/run/extract``), so it
is run against the base code:

    git worktree add <base> <base commit>
    python tests/integration/benchmark/fixtures/gen_tolerance_default_golden.py \
        --oracles-root <base>/python --out tests/integration/benchmark/fixtures/tolerance_default_golden.json

The installed spectrafit-core is imported first, so only ``oracles`` comes from
``--oracles-root``. Run with ``OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=
RAYON_NUM_THREADS=1``.

The golden also records the recording host's CPU fingerprint (``host_fingerprint``).
spectrafit's Rust core uses faer, which selects CPU-specific SIMD kernels at runtime;
jax compiles every fit with XLA for the host ISA; and lmfit and the scipy
``least_squares`` backends run through OpenBLAS and NumPy, which select CPU-specific
BLAS/SIMD kernels at runtime. So every row reproduces bit for bit only on a host with
the same fingerprint.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

GOLDEN_CASES: tuple[str, ...] = (
    "EZ-001",
    "CX-001",
    "RL-001",
    "OF-001",
    "SC-001",
    "ED-001",
    "LS-001",
    "FX-001",
    "TI-001",
    "RB-001",
)
"""The first case of every benchmark category."""


FINGERPRINT_FLAGS: tuple[str, ...] = ("avx2", "avx512f", "fma")
"""The CPU flags XLA's generated code depends on."""


def host_fingerprint(cpuinfo: Path = Path("/proc/cpuinfo")) -> dict[str, Any]:
    """CPU model name and the ``FINGERPRINT_FLAGS`` the CPU has, read from ``cpuinfo``.

    Without a readable ``cpuinfo`` the model is ``None`` and every flag ``False``, a value
    no recorded golden carries.
    """
    try:
        text = cpuinfo.read_text(encoding="utf-8")
    except OSError:
        text = ""
    model: str | None = None
    flags: set[str] | None = None
    for line in text.splitlines():
        key, _, value = line.partition(":")
        match key.strip():
            case "model name" if model is None:
                model = value.strip()
            case "flags" if flags is None:
                flags = set(value.split())
            case _:
                pass
    present = flags or set()
    return {"cpu_model": model, **{f: f in present for f in FINGERPRINT_FLAGS}}


def hexf(v: float | None) -> str | None:
    """Exact, NaN-safe float encoding."""
    return None if v is None else float(v).hex()


def digest(values: Any) -> str:
    """sha256 of a float64 array's bytes."""
    return hashlib.sha256(np.ascontiguousarray(values, dtype=np.float64).tobytes()).hexdigest()


def outcome_record(out: Any) -> dict[str, Any]:
    """Deterministic fields of a ``BackendOutcome`` (no timing)."""
    return {
        "success": bool(out.success),
        "r2": hexf(out.r2),
        "chi2": hexf(out.chi2),
        "reduced_chi2": hexf(out.reduced_chi2),
        "aic": hexf(out.aic),
        "bic": hexf(out.bic),
        "n_iter": int(out.n_iter),
        "params": {k: hexf(v) for k, v in sorted(out.params.items())},
        "param_stderr": {k: hexf(v) for k, v in sorted(out.param_stderr.items())},
        "best_fit_sha256": digest(out.best_fit),
        "cost_history_sha256": digest(out.cost_history),
        "jacobian_condition_number": hexf(out.jacobian_condition_number),
        "fit_dof": out.fit_dof,
    }


def run_golden(backends: list[Any], cases: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """``{backend: {case: record}}`` for every backend and golden case."""
    out: dict[str, dict[str, Any]] = {}
    for b in backends:
        rows: dict[str, Any] = {}
        for cid in GOLDEN_CASES:
            case = cases[cid]
            if not b.is_supported(case):
                rows[cid] = {"supported": False}
                continue
            rows[cid] = {
                "supported": True,
                **outcome_record(b.extract(b.run(b.build(case), case), case)),
            }
        out[b.name] = rows
    return out


def main() -> None:
    """Write the golden JSON."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--oracles-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    import spectrafit_core  # noqa: F401  # bind the installed build before oracles is imported

    sys.path.insert(0, str(args.oracles_root.resolve()))
    import oracles
    from oracles.backends import get_backends
    from oracles.cases import build_catalog

    cases = {c.id: c for c in build_catalog()}
    commit = subprocess.run(
        ["git", "-C", str(args.oracles_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    record = {
        "oracles_commit": commit,
        "oracles_file": str(Path(oracles.__file__).resolve()),
        "versions": {
            p: md.version(p)
            for p in ("spectrafit-core", "lmfit", "scipy", "numpy", "jax", "optimistix")
        },
        "host": host_fingerprint(),
        "cases": list(GOLDEN_CASES),
        "outcomes": run_golden(get_backends(), cases),
    }
    args.out.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
