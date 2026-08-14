#!/usr/bin/env bash
# Runs ON the benchmark host, detached. Copied there by scripts/remote_bench.sh.
#
# Kept as its own file rather than inlined into an ssh heredoc: the launcher
# needs three levels of quoting (local shell -> ssh -> remote heredoc) and
# nested heredocs there are unreadable and silently fragile.
#
# Expects: REPO, RUNDIR, REPS, MC in the environment.
set -uo pipefail

cd "$REPO"

# reports.py hardcodes REPORTS_ROOT = Path(".spectrafit_reports") relative to
# CWD — there is no environment override. So the run lands in the repo as usual
# and we CLAIM the produced directory afterwards, recording which one it was.
before="$(ls -1 .spectrafit_reports/benchmark 2>/dev/null | sort | tail -1 || true)"

UV_CACHE_DIR=.uv-cache PYTHONPATH=python \
    uv run --no-sync python -m oracles.cli run --reps "$REPS" --mc "$MC"
status=$?

after="$(ls -1 .spectrafit_reports/benchmark 2>/dev/null | sort | tail -1 || true)"

{
    echo "exit_status=$status"
    echo "finished_utc=$(date -u +%FT%TZ)"
    [ -n "$after" ] && [ "$after" != "$before" ] && echo "run_dir=$after"
} >> "$RUNDIR/RUNINFO"

# Copy rather than move: leaving the run in place keeps the repo's own
# allocate_run_dir counter monotonic, so a later run on this host cannot be
# handed a number that is already in use elsewhere.
if [ -n "$after" ] && [ "$after" != "$before" ]; then
    cp -r ".spectrafit_reports/benchmark/$after" "$RUNDIR/run"
fi

echo "$status" > "$RUNDIR/COMPLETE"
