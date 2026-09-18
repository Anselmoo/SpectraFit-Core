"""Run the benchmark at a ladder of repetition depths, with FAIR provenance.

WHY THIS EXISTS. The manuscript's measurement-stability paragraph quotes five
geometric means across a reps ladder. Four of them cannot be recomputed by a
reader: the ladder ran in CI, the artifacts expired after 30 days, and only the
canonical rung's derived summary was committed. A claim about measurement
convergence that rests on numbers nobody can regenerate is the weakest kind of
evidence a paper about verifiable claims can offer.

Two properties of the existing harness make that worse, and this script works
around both rather than changing them:

1. RUN IDS COLLIDE ACROSS MACHINES. ``allocate_run_dir`` numbers runs from the
   directories present on the LOCAL host, so every clean machine produces
   ``<date>_run_001``. The published dashboard and the manuscript currently
   quote different figures under exactly that one label. Each rung here gets a
   ``run_uid`` derived from host, UTC timestamp and commit, which cannot
   collide.

2. THE SUITE HALVES ``--reps``. ``run_suite`` is called with
   ``n_reps=max(1, n_reps // 2)``, so ``--reps 25`` times each case twelve
   times, and ``--reps 1`` and ``--reps 2`` are the SAME measurement. The
   solver is deliberately not changed — the perf baseline, the gate thresholds
   and two dozen historical runs all depend on current behaviour. Instead the
   ladder is chosen so the EFFECTIVE depths are distinct, and every record
   carries both ``reps_requested`` and ``reps_effective`` so the distinction can
   never be lost again.

The manifest a run already writes records results and almost no provenance: no
reps, no commit, no host, no CPU, no seed, no timestamps. This adds them
alongside rather than patching the manifest schema, which is contract-guarded.

Usage:
    python scripts/bench_ladder.py --out DIR [--ladder 2,4,10,25,50,100] [--mc 8]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPORTS = REPO / ".spectrafit_reports" / "benchmark"

# Chosen so `reps // 2` yields 1, 2, 5, 12, 25, 50 — six DISTINCT suite depths.
# A naive 1,2,10,25,50,100 wastes a rung: 1 and 2 both collapse to 1.
DEFAULT_LADDER = "2,4,10,25,50,100"

# WHY THIS IS SET. The first ladder run died on every rung with SIGSEGV/SIGABRT
# and "LLVM compilation error: Cannot allocate memory", 16 threads deep — one
# per core. jax's XLA sizes its intra-op thread pool to the core count, and each
# thread JIT-compiles independently; on a 16-core host the transient cost of
# concurrent LLVM compilation across 127 distinct case layouts exhausted 31 GiB.
# The benchmark engine itself does not parallelise, so this is entirely jax's
# internal pool. This is the first time jax has ever run in this benchmark, so
# nothing could have surfaced it earlier.
#
# Measured on that host over all 127 jax-eligible cases:
#     unconstrained                  -> OOM, every rung dead
#     with these flags               -> peak RSS 1.54 GB
#
# Deliberately NOT setting RAYON_NUM_THREADS / OMP_NUM_THREADS here, though they
# also stop the OOM: rayon is what spectrafit-core's own Rust core uses, so
# pinning it would throttle the subject, change what the benchmark measures, and
# break comparability with every previously recorded run. These flags constrain
# only the comparator's compiler, which is the actual fault.
JAX_XLA_FLAGS = "--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1"


def _sh(*cmd: str, cwd: Path | None = None) -> str:
    """Run a command and return stripped stdout, or '' if it fails."""
    try:
        out = subprocess.run(
            cmd,
            cwd=cwd or REPO,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _pkg_version(name: str) -> str | None:
    """Installed version of *name*, or None when the package is absent."""
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:  # noqa: BLE001 - absence is a legitimate answer here
        return None


def _cpu_model() -> str:
    """Human-readable CPU model, best effort across Linux and macOS."""
    if Path("/proc/cpuinfo").exists():
        text = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
        if m := re.search(r"^model name\s*:\s*(.+)$", text, re.MULTILINE):
            return m.group(1).strip()
    return _sh("sysctl", "-n", "machdep.cpu.brand_string") or platform.processor() or "unknown"


def _ram_gb() -> float | None:
    """Total RAM in GiB, or None if it cannot be determined."""
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
    except (ValueError, OSError):
        return None


def environment() -> dict:
    """Capture everything needed to interpret a timing number later.

    This is the FAIR-R half: a speedup ratio is meaningless without the machine
    and the library versions that produced it, and absolute times are not
    portable at all.
    """
    commit = _sh("git", "rev-parse", "HEAD")
    return {
        "git": {
            "commit": commit,
            "branch": _sh("git", "rev-parse", "--abbrev-ref", "HEAD"),
            # A dirty tree means the commit does not identify the code that ran.
            "dirty": bool(_sh("git", "status", "--porcelain")),
        },
        "host": {
            "hostname": platform.node(),
            "cpu": _cpu_model(),
            "cores": os.cpu_count(),
            "ram_gb": _ram_gb(),
            "os": platform.platform(),
            "kernel": platform.release(),
        },
        "versions": {
            "python": platform.python_version(),
            "rustc": (_sh("rustc", "--version") or "absent").replace("rustc ", ""),
            **{
                p: _pkg_version(p)
                for p in (
                    "numpy",
                    "scipy",
                    "lmfit",
                    "jax",
                    "jaxlib",
                    "optimistix",
                    "spectrafit-core",
                )
            },
        },
    }


def run_uid(env: dict, started: str, reps: int) -> str:
    """Collision-proof identifier: host, start time, commit and depth."""
    raw = f"{env['host']['hostname']}|{started}|{env['git']['commit']}|{reps}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def newest_run() -> str | None:
    """Name of the most recent run directory, or None."""
    if not REPORTS.is_dir():
        return None
    runs = sorted(d.name for d in REPORTS.iterdir() if d.is_dir())
    return runs[-1] if runs else None


def one_rung(reps: int, mc: int, out: Path, env: dict) -> dict:
    """Run a single rung and return its provenance record."""
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    uid = run_uid(env, started, reps)
    effective = max(1, reps // 2)
    dest = out / f"rung_{effective:03d}"
    dest.mkdir(parents=True, exist_ok=True)

    before = newest_run()
    print(f"  rung reps={reps} (suite depth {effective}) -> {dest.name}", flush=True)

    proc = subprocess.run(
        [sys.executable, "-m", "oracles.cli", "run", "--reps", str(reps), "--mc", str(mc)],
        cwd=REPO,
        env={
            **os.environ,
            "PYTHONPATH": str(REPO / "python"),
            # Prepend so an operator-supplied XLA_FLAGS still wins.
            "XLA_FLAGS": f"{JAX_XLA_FLAGS} {os.environ.get('XLA_FLAGS', '')}".strip(),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    finished = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    (dest / "run.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")

    after = newest_run()
    produced = after if after and after != before else None
    headline: dict = {}
    if produced:
        # Copy, don't move: leaving it in place keeps allocate_run_dir's counter
        # monotonic so a later run cannot be handed a number already in use.
        shutil.copytree(REPORTS / produced, dest / "run", dirs_exist_ok=True)
        mf = dest / "run" / "manifest.json"
        if mf.exists():
            m = json.loads(mf.read_text(encoding="utf-8"))
            headline = {
                k: m.get(k)
                for k in (
                    "geomean_speedup_vs_baseline",
                    "harmonic_mean_speedup_vs_baseline",
                    "max_abs_delta_r2",
                    "spectrafit_win_rate",
                    "n_cases",
                    "regressions",
                    "backends",
                    "saturated_categories",
                )
            }

    record = {
        "run_uid": uid,
        "schema": "spectrafit-core/bench-provenance/1",
        "params": {
            # BOTH depths, always. Recording only one is how the manuscript came
            # to describe a 12-repetition run as "N=25".
            "reps_requested": reps,
            "reps_effective": effective,
            "mc": mc,
            "seed": 20260603,  # oracles.cases.build_catalog default
            "xla_flags": JAX_XLA_FLAGS,
        },
        "timing": {"started_utc": started, "finished_utc": finished},
        "exit_status": proc.returncode,
        "local_run_dir": produced,
        "headline": headline,
        **env,
    }
    (dest / "provenance.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> int:
    """Run every rung, then write the aggregate ladder record."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--ladder", default=DEFAULT_LADDER)
    ap.add_argument("--mc", type=int, default=8)
    args = ap.parse_args()

    rungs = [int(x) for x in args.ladder.split(",") if x.strip()]
    args.out.mkdir(parents=True, exist_ok=True)
    env = environment()
    print(
        f"ladder {rungs} on {env['host']['hostname']} "
        f"({env['host']['cores']} cores) @ {env['git']['commit'][:8]}",
        flush=True,
    )

    records = [one_rung(r, args.mc, args.out, env) for r in rungs]

    ladder = {
        "schema": "spectrafit-core/bench-ladder/1",
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": env,
        "rungs": [
            {
                "run_uid": r["run_uid"],
                "reps_requested": r["params"]["reps_requested"],
                "reps_effective": r["params"]["reps_effective"],
                "exit_status": r["exit_status"],
                **r["headline"],
            }
            for r in records
        ],
    }
    (args.out / "ladder.json").write_text(json.dumps(ladder, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {args.out / 'ladder.json'} ({len(records)} rungs)")
    return 0 if all(r["exit_status"] == 0 for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
