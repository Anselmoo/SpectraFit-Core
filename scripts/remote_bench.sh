#!/usr/bin/env bash
# Drive a long benchmark run on a remote machine, detached, and fetch it back.
#
# WHY THIS EXISTS. The full suite at a high repetition count takes hours. Run it
# on a shared CI runner and you measure the contention, not the solver; run it
# over a plain `ssh` and it dies with the connection. This wraps the three
# things that actually matter: get the current branch onto the remote, launch
# the run under `nohup` in its OWN directory so a second run cannot collide with
# the first, and pull the artifacts back afterwards.
#
# RUN DIRECTORIES ARE NOT UNIQUE ACROSS MACHINES. `allocate_run_dir` numbers
# runs from the directories present on the local host, so a clean machine always
# produces `<date>_run_001`. That is how the published dashboard and the JORS
# manuscript ended up quoting different figures under one identifier. Every run
# launched here therefore gets its own timestamped, host-tagged directory under
# ~/bench-runs/, and the tag is recorded in RUNINFO so the provenance survives
# the trip home.
#
#   poe terra_push     — put the current branch on the remote, sync, build
#   poe terra_bench    — launch a detached run (REPS=25 default)
#   poe terra_status   — is it alive, how far along, tail of the log
#   poe terra_pull     — copy the finished run back into .spectrafit_reports/
#
# Override the host with REMOTE=<ssh-host>, the depth with REPS=<n>.
set -euo pipefail

REMOTE="${REMOTE:-terra}"
REPS="${REPS:-25}"
MC="${MC:-4}"
REMOTE_REPO="${REMOTE_REPO:-~/projects/spectrafit-core}"
RUNS_ROOT="${RUNS_ROOT:-~/bench-runs}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)

# `ssh -t` is deliberately NOT used: it allocates a tty, and a tty is what makes
# a detached job die with the connection.
rsh() { ssh "${SSH_OPTS[@]}" "$REMOTE" "bash -lc '$1'"; }

branch_here() { git rev-parse --abbrev-ref HEAD; }
sha_here()    { git rev-parse HEAD; }

cmd_push() {
    local br sha
    br="$(branch_here)"; sha="$(sha_here)"
    echo "==> pushing $br ($(echo "$sha" | cut -c1-8)) to $REMOTE"
    git push --quiet origin "HEAD:$br" 2>/dev/null || \
        git push --quiet gitlab "HEAD:$br"
    rsh "set -e
        cd $REMOTE_REPO
        git fetch --quiet origin '$br:refs/remotes/origin/$br' --force
        git checkout --quiet -B bench/local 'origin/$br'
        test \"\$(git rev-parse HEAD)\" = '$sha' || { echo 'REMOTE SHA MISMATCH'; exit 1; }
        export UV_CACHE_DIR=.uv-cache
        uv sync --inexact --extra benchmark --extra jax 2>&1 | tail -3
        # --release is not optional: a debug extension runs orders of magnitude
        # slower and would measure the build profile rather than the solver.
        uv run --no-sync maturin develop --release 2>&1 | tail -3
        echo \"remote now at \$(git rev-parse --short HEAD)\""
}

cmd_bench() {
    local tag; tag="$(date -u +%Y%m%dT%H%M%SZ)"
    echo "==> launching detached run reps=$REPS mc=$MC on $REMOTE (tag $tag)"
    scp -q -o BatchMode=yes scripts/remote_bench_worker.sh "$REMOTE:/tmp/rbw.sh"
    rsh "set -e
        cd $REMOTE_REPO
        RUNDIR=$RUNS_ROOT/$tag
        mkdir -p \$RUNDIR
        install -m 755 /tmp/rbw.sh \$RUNDIR/worker.sh
        { echo tag=$tag
          echo host=\$(hostname)
          echo cores=\$(nproc)
          echo commit=\$(git rev-parse HEAD)
          echo branch=\$(git rev-parse --abbrev-ref HEAD)
          echo reps=$REPS
          echo mc=$MC
          echo started_utc=\$(date -u +%FT%TZ)
        } > \$RUNDIR/RUNINFO
        # setsid + </dev/null so the job outlives this ssh session entirely.
        REPO=$REMOTE_REPO RUNDIR=\$RUNDIR REPS=$REPS MC=$MC \
          nohup setsid \$RUNDIR/worker.sh > \$RUNDIR/run.log 2>&1 < /dev/null &
        echo \$! > \$RUNDIR/PID
        ln -sfn \$RUNDIR $RUNS_ROOT/latest
        sleep 3
        echo \"  launched pid \$(cat \$RUNDIR/PID) -> \$RUNDIR\"
        kill -0 \$(cat \$RUNDIR/PID) 2>/dev/null && echo '  alive: yes' || echo '  alive: NO'"
}

cmd_ladder() {
    local tag; tag="ladder-$(date -u +%Y%m%dT%H%M%SZ)"
    local rungs="${LADDER:-2,4,10,25,50,100}"
    echo "==> launching detached LADDER $rungs mc=$MC on $REMOTE (tag $tag)"
    scp -q -o BatchMode=yes scripts/bench_ladder.py "$REMOTE:/tmp/bench_ladder.py"
    rsh "set -e
        cd $REMOTE_REPO
        cp /tmp/bench_ladder.py scripts/bench_ladder.py
        RUNDIR=$RUNS_ROOT/$tag
        mkdir -p \$RUNDIR
        # Rungs run smallest-first and each writes its provenance as it finishes,
        # so an interrupted ladder still yields usable, fully-described rungs.
        UV_CACHE_DIR=.uv-cache PYTHONPATH=python \
          nohup setsid uv run --no-sync python scripts/bench_ladder.py \
            --out \$RUNDIR --ladder $rungs --mc $MC \
            > \$RUNDIR/ladder.log 2>&1 < /dev/null &
        echo \$! > \$RUNDIR/PID
        ln -sfn \$RUNDIR $RUNS_ROOT/latest
        sleep 3
        echo \"  launched pid \$(cat \$RUNDIR/PID) -> \$RUNDIR\"
        kill -0 \$(cat \$RUNDIR/PID) 2>/dev/null && echo '  alive: yes' || echo '  alive: NO'"
}

cmd_status() {
    rsh "set -e
        cd $RUNS_ROOT/latest 2>/dev/null || { echo 'no run launched'; exit 0; }
        cat RUNINFO | sed 's/^/  /'
        pid=\$(cat PID 2>/dev/null || echo 0)
        if kill -0 \$pid 2>/dev/null; then
            echo \"  state=RUNNING pid=\$pid elapsed=\$(ps -o etime= -p \$pid | tr -d ' ')\"
        else
            echo '  state=FINISHED (or died — check the log tail)'
        fi
        echo \"  cases done: \$(grep -ci 'ok\\|done' run.log 2>/dev/null || echo 0)\"
        echo '  --- last 12 log lines ---'
        tail -12 run.log 2>/dev/null | sed 's/^/  /'
        echo '  --- rungs completed ---'
        for pj in rung_*/provenance.json; do
            [ -f \"\$pj\" ] || continue
            python3 -c \"
import json,sys
r=json.load(open(sys.argv[1]))
h=r.get('headline') or {}
print('   rung reps=%-4s depth=%-3s exit=%s geomean=%s' % (
    r['params']['reps_requested'], r['params']['reps_effective'],
    r['exit_status'], h.get('geomean_speedup_vs_baseline')))\" \"\$pj\"
        done
        [ -f ladder.json ] && echo '  LADDER COMPLETE: ladder.json written'"
}

cmd_pull() {
    local dest="${DEST:-.spectrafit_reports/remote}"
    mkdir -p "$dest"
    echo "==> pulling from $REMOTE:$RUNS_ROOT/latest -> $dest"
    # -L so the `latest` symlink is followed rather than copied as a link.
    scp -q -r -o BatchMode=yes "$REMOTE:$RUNS_ROOT/latest/" "$dest/" 2>/dev/null \
        || rsync -az --copy-links "$REMOTE:$RUNS_ROOT/latest/" "$dest/"
    echo "  fetched into $dest"
    find "$dest" -name manifest.json | sed 's/^/  /'
}

case "${1:-}" in
    push)   cmd_push ;;
    ladder) cmd_ladder ;;
    bench)  cmd_bench ;;
    status) cmd_status ;;
    pull)   cmd_pull ;;
    *) echo "usage: $0 {push|bench|ladder|status|pull}   [REMOTE=host REPS=n MC=n]" >&2; exit 2 ;;
esac
