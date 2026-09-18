#!/usr/bin/env python3
"""Run the benchmark detached, for a workstation that can afford the wall clock.

Why this exists. The citation-grade rung (reps=100) needs about 6.8 h by the
measured cost model in `.gitlab/55-deep-bench.yml`, against a 3 h GitLab project
timeout and a shared-runner budget that makes a 7 h job a decision about other
people's capacity. A local 16-core / 32 GB box has neither constraint. This
script drives the same `oracles.cli` entry point CI uses, detached from the
terminal, so the run survives the shell closing and reports progress to a log.

    uv run poe bench_bg              # detached ladder, default rungs
    uv run poe bench_bg_status       # is it alive, how far along
    uv run poe bench_bg_stop         # terminate the run

Direct use, when the poe wrappers are not what you want:

    uv run python scripts/bench_background.py start --reps 1,2,5,10,25,50,100
    uv run python scripts/bench_background.py status
    uv run python scripts/bench_background.py collect --out artifacts/deep
    uv run python scripts/bench_background.py stop

Deliberately NOT parallel across rungs. The CI matrix runs its cells on separate
runners; here they would share one machine, and concurrent runs would contend
for the same cores while the thing being measured IS core-seconds. Rungs run in
sequence, cheapest first, so a partial ladder is still a usable ladder — if the
box is needed for something else after four hours, the rungs already finished
are valid and `collect` will merge exactly those.

The memory-hazard hook in this repo blocks unbounded benchmark invocations for
good reason (a full MC ensemble writes a ~46 MB results.json per rung, and an
unattended sweep can fill a disk). This script is bounded by construction: rungs
are explicit, `--mc` is passed through with the same default CI uses, and
`collect` copies only the small manifest/trust sidecars plus one results.json
per rung into the output directory.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".spectrafit_reports" / "background-jobs"
PID_FILE = STATE_DIR / "bench_bg.pid"
LOG_FILE = STATE_DIR / "bench_bg.log"
PLAN_FILE = STATE_DIR / "bench_bg.json"

DEFAULT_REPS = "1,2,5,10,25"
DEFAULT_MC = 4

# Measured on GWDG shared runners (pipeline 366747): a two-parameter fit over
# four completed cells that then predicted the rest to within seconds. A local
# box is typically ~3x faster per rep, but the SHAPE holds — fixed overhead
# dominates the cheap rungs — so this is used only to print an estimate, never
# to decide anything.
FIXED_S, PER_REP_S = 3298.0, 210.0


def _fmt(seconds: float) -> str:
    h, m = divmod(int(seconds) // 60, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"


def estimate(reps: list[int], speedup: float) -> float:
    """Total wall clock for a sequential ladder, scaled by a local speed factor."""
    return sum(FIXED_S + r * PER_REP_S for r in reps) / speedup


def _run_dirs() -> list[Path]:
    root = REPO / ".spectrafit_reports" / "benchmark"
    return sorted((p for p in root.glob("*") if p.is_dir()), key=lambda p: p.name)


def cmd_start(args: argparse.Namespace) -> int:
    """Spawn the detached ladder and record its pid and plan."""
    if PID_FILE.exists() and _alive(int(PID_FILE.read_text().strip() or 0)):
        print(f"already running (pid {PID_FILE.read_text().strip()}) — stop it first")
        return 1

    reps = [int(r) for r in args.reps.split(",") if r.strip()]
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    est = estimate(reps, args.assume_speedup)
    print(f"rungs      : {reps}")
    print(f"mc         : {args.mc}")
    print(f"estimate   : ~{_fmt(est)} sequential (assuming {args.assume_speedup:g}x the")
    print("             measured GWDG rate; the estimate is advisory only)")
    print(f"log        : {LOG_FILE}")

    # One shell running the rungs in sequence. `setsid` detaches it from this
    # terminal's process group so closing the shell does not take it with us.
    inner = " && ".join(
        f'echo "=== reps={r} $(date -Iseconds) ===" && '
        f"PYTHONPATH=python python -m oracles.cli run --reps {r} --mc {args.mc}"
        for r in reps
    )
    script = f'{inner} ; echo "=== LADDER DONE $(date -Iseconds) ==="'

    with LOG_FILE.open("a") as log:
        proc = subprocess.Popen(
            ["/bin/bash", "-lc", script],
            cwd=REPO,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

    PID_FILE.write_text(str(proc.pid))
    PLAN_FILE.write_text(
        json.dumps(
            {
                "pid": proc.pid,
                "reps": reps,
                "mc": args.mc,
                "started_at": datetime.now(UTC).isoformat(),
                "estimate_seconds": est,
                "runs_before": [p.name for p in _run_dirs()],
            },
            indent=2,
        )
        + "\n",
    )
    print(f"\nstarted pid {proc.pid} — detached; safe to close this shell")
    return 0


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def cmd_status(_: argparse.Namespace) -> int:
    """Report liveness, elapsed time, and which rungs have produced a run dir."""
    if not PLAN_FILE.exists():
        print("no background benchmark has been started")
        return 1
    plan = json.loads(PLAN_FILE.read_text())
    pid = plan["pid"]
    running = _alive(pid)

    started = datetime.fromisoformat(plan["started_at"])
    elapsed = (datetime.now(UTC) - started).total_seconds()
    new = [p.name for p in _run_dirs() if p.name not in set(plan["runs_before"])]

    print(f"pid        : {pid} ({'running' if running else 'not running'})")
    print(f"started    : {plan['started_at']}")
    print(f"elapsed    : {_fmt(elapsed)} of ~{_fmt(plan['estimate_seconds'])} estimated")
    print(f"rungs      : {plan['reps']}")
    print(f"completed  : {len(new)} run dir(s) since start")
    for name in new:
        print(f"             {name}")
    if LOG_FILE.exists():
        tail = LOG_FILE.read_text().splitlines()[-3:]
        print("log tail   : " + ("\n             ".join(tail) if tail else "(empty)"))
    return 0 if running or new else 1


def cmd_collect(args: argparse.Namespace) -> int:
    """Copy each completed rung into the CI artifact layout for the figures.

    Produces `<out>/reps-<N>/{results,manifest,trust}.json`, the same shape
    `benchmark:deep` uploads, so `extract_bench_summary.py` and the figure
    scripts consume a local ladder and a CI ladder identically.
    """
    if not PLAN_FILE.exists():
        print("no background benchmark has been started")
        return 1
    plan = json.loads(PLAN_FILE.read_text())
    before = set(plan["runs_before"])
    new = [p for p in _run_dirs() if p.name not in before]
    if not new:
        print("no completed runs to collect")
        return 1

    # Runs land in start order, so the Nth new run dir is the Nth rung. A rung
    # that never finished simply has no dir, and is skipped rather than guessed.
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for reps, run_dir in zip(plan["reps"], new, strict=False):
        dest = out / f"reps-{reps}"
        dest.mkdir(parents=True, exist_ok=True)
        copied = []
        for name in ("results.json", "manifest.json", "trust.json"):
            src = run_dir / name
            if src.exists():
                shutil.copy2(src, dest / name)
                copied.append(name)
        print(f"reps-{reps:<4} <- {run_dir.name}  ({', '.join(copied) or 'nothing'})")
    if len(new) < len(plan["reps"]):
        print(
            f"\nNOTE only {len(new)} of {len(plan['reps'])} rungs completed — "
            "collected the partial ladder, which is still usable; the missing "
            "rungs are absent, not approximated.",
        )
    return 0


def cmd_stop(_: argparse.Namespace) -> int:
    """Terminate the detached ladder, leaving completed rungs on disk."""
    if not PID_FILE.exists():
        print("no pid file — nothing to stop")
        return 1
    pid = int(PID_FILE.read_text().strip() or 0)
    if not _alive(pid):
        print(f"pid {pid} is not running")
        PID_FILE.unlink(missing_ok=True)
        return 1
    # Kill the whole process group: the pid is a bash wrapper, and signalling
    # only it would orphan the python child mid-rung.
    os.killpg(os.getpgid(pid), signal.SIGTERM)
    time.sleep(2)
    if _alive(pid):
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    PID_FILE.unlink(missing_ok=True)
    print(f"stopped {pid}; completed rungs remain in .spectrafit_reports/benchmark/")
    return 0


def main() -> int:
    """Dispatch the subcommand."""
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="spawn the detached ladder")
    s.add_argument("--reps", default=DEFAULT_REPS, help=f"comma-separated (default {DEFAULT_REPS})")
    s.add_argument("--mc", type=int, default=DEFAULT_MC)
    s.add_argument(
        "--assume-speedup",
        type=float,
        default=3.0,
        help="local speed relative to the measured GWDG rate; affects the printed estimate only",
    )
    s.set_defaults(fn=cmd_start)

    sub.add_parser("status", help="liveness and progress").set_defaults(fn=cmd_status)
    sub.add_parser("stop", help="terminate the run").set_defaults(fn=cmd_stop)

    c = sub.add_parser("collect", help="copy rungs into the CI artifact layout")
    c.add_argument("--out", default="artifacts/deep")
    c.set_defaults(fn=cmd_collect)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
