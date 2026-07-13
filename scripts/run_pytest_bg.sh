#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

usage() {
  cat <<'EOF'
run_pytest_bg.sh — submit long-running pytest/poe jobs in the background

Usage:
  ./scripts/run_pytest_bg.sh [--label NAME] --poe TASK
  ./scripts/run_pytest_bg.sh [--label NAME] --pytest [ARGS...]
  ./scripts/run_pytest_bg.sh [--label NAME] --command "CUSTOM COMMAND"

Examples:
  ./scripts/run_pytest_bg.sh --poe benchmark_speedboat
  ./scripts/run_pytest_bg.sh --label qv-full --poe quick_validation_tests
  ./scripts/run_pytest_bg.sh --pytest tests/speedboat/ -m speedboat -v
  ./scripts/run_pytest_bg.sh --label one-case --command "PYTHONPATH=python uv run pytest tests/quick_validation/test_single_gaussian.py -v"

Each submission creates:
  .spectrafit_reports/background-jobs/<family>/<NNN>/job.log   stdout/stderr log
  .spectrafit_reports/background-jobs/<family>/<NNN>/job.json  metadata + status seed
  .spectrafit_reports/background-jobs/<family>/<NNN>/job.pid   process id
  .pytest_logs/<job-id>.*                                         compatibility mirror
EOF
}

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
LEGACY_DIR="$ROOT_DIR/.pytest_logs"
RUNS_ROOT="$ROOT_DIR/.spectrafit_reports/background-jobs"
mkdir -p "$LEGACY_DIR" "$RUNS_ROOT"
JOBS_JSON="$RUNS_ROOT/jobs.json"
JOBS_LOG="$RUNS_ROOT/jobs.log"

LABEL=""
MODE=""
COMMAND=""

build_prefixed_command() {
  local raw_command=$1
  printf "source /home/cloud/.scripts/env.sh >/dev/null 2>&1 && cd '%s' && %s" "$ROOT_DIR" "$raw_command"
}

sanitize_label() {
  printf '%s' "$1" | tr ' /:' '---' | tr -cd '[:alnum:]_.-'
}

allocate_run_dir() {
  local family=$1
  python3 - <<'PY' "$RUNS_ROOT" "$family"
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
family = sys.argv[2]
family_dir = root / family
family_dir.mkdir(parents=True, exist_ok=True)

existing = [
    int(path.name)
    for path in family_dir.iterdir()
    if path.is_dir() and path.name.isdigit() and len(path.name) == 3
]
next_num = (max(existing) + 1) if existing else 1
run_dir = family_dir / f"{next_num:03d}"
run_dir.mkdir(parents=True, exist_ok=False)
print(run_dir)
PY
}

link_legacy_path() {
  local source_path=$1
  local legacy_path=$2
  ln -sfn "$source_path" "$legacy_path"
}

write_metadata() {
  local metadata_path=$1
  local status=$2
  local job_id=$3
  local pid=$4
  local started_at=$5
  local started_at_bern=$6
  local label=$7
  local mode=$8
  local log_path=$9
  local command=${10}
  local target_repo=${11}
  local target_repo_root=${12}
  local target_reports_root=${13}
  local target_tests_root=${14}
  local export_root=${15}
  local expected_exports=${16}

  python3 - <<'PY' "$metadata_path" "$status" "$job_id" "$pid" "$started_at" "$started_at_bern" "$label" "$mode" "$log_path" "$command" "$target_repo" "$target_repo_root" "$target_reports_root" "$target_tests_root" "$export_root" "$expected_exports"
import json
import sys

path, status, job_id, pid, started_at, started_at_bern, label, mode, log_path, command, target_repo, target_repo_root, target_reports_root, target_tests_root, export_root, expected_exports = sys.argv[1:]
payload = {
    "job_id": job_id,
    "status": status,
    "pid": int(pid),
    "started_at": started_at,
    "started_at_bern": started_at_bern,
    "timezone": "Europe/Zurich",
    "label": label,
    "mode": mode,
    "log_path": log_path,
    "command": command,
    "target_repo": target_repo,
    "target_repo_root": target_repo_root,
    "target_reports_root": target_reports_root,
    "target_tests_root": target_tests_root,
    "export_root": export_root,
    "expected_exports": json.loads(expected_exports),
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
PY
}

infer_target_repo() {
  local remote_url
  remote_url=$(git -C "$ROOT_DIR" config --get remote.origin.url 2>/dev/null || true)
  if [ -z "$remote_url" ]; then
    printf '%s' "$(basename "$ROOT_DIR")"
    return
  fi

  python3 - <<'PY' "$remote_url" "$ROOT_DIR"
import re
import sys
from pathlib import Path

remote_url = sys.argv[1].strip()
root_dir = Path(sys.argv[2]).name

match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote_url)
if match:
    print(f"{match.group(1)}/{match.group(2)}")
else:
    print(root_dir)
PY
}

_infer_export_info() {
  local label=$1
  local root_dir=$2
  python3 - <<'PY' "$label" "$root_dir"
import json
import sys

label = sys.argv[1].lower()
root = sys.argv[2]

if "benchmark-10k" in label or "10k" in label:
    export_root = f"{root}/benchmark"
    stems = ["scaling_10k.json", "scaling_10k.html", "scaling_10k.pdf"]
elif "benchmark" in label:
    export_root = f"{root}/benchmark"
    stems = ["results.json", "results.html", "results.pdf"]
elif "qv" in label:
    export_root = f"{root}/.spectrafit_reports/quick-validation"
    stems = []
elif "speedboat" in label:
    export_root = ""
    stems = []
else:
    export_root = ""
    stems = []

expected = [f"{export_root}/{s}" for s in stems] if export_root and stems else []
print(export_root)
print(json.dumps(expected))
PY
}

if [ "$#" -eq 0 ]; then
  usage
  exit 1
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    --label)
      LABEL=${2:-}
      [ -n "$LABEL" ] || { echo "Missing value after --label" >&2; exit 1; }
      shift 2
      ;;
    --poe)
      MODE="poe"
      TASK=${2:-}
      [ -n "$TASK" ] || { echo "Missing task after --poe" >&2; exit 1; }
      shift 2
      POE_ARGS=("$@")
      if [ "${#POE_ARGS[@]}" -gt 0 ]; then
        printf -v POE_ARG_STRING '%q ' "${POE_ARGS[@]}"
        COMMAND=$(build_prefixed_command "uv run poe $TASK ${POE_ARG_STRING% }")
      else
        COMMAND=$(build_prefixed_command "uv run poe $TASK")
      fi
      break
      ;;
    --pytest)
      MODE="pytest"
      shift
      [ "$#" -gt 0 ] || { echo "Provide pytest arguments after --pytest" >&2; exit 1; }
      PYTEST_ARGS=("$@")
      printf -v ARG_STRING '%q ' "${PYTEST_ARGS[@]}"
      COMMAND=$(build_prefixed_command "PYTHONPATH=python uv run pytest ${ARG_STRING% }")
      break
      ;;
    --command)
      MODE="command"
      RAW_COMMAND=${2:-}
      [ -n "$RAW_COMMAND" ] || { echo "Missing command after --command" >&2; exit 1; }
      COMMAND=$(build_prefixed_command "$RAW_COMMAND")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

[ -n "$MODE" ] || { echo "Choose one of --poe, --pytest, or --command" >&2; exit 1; }
[ -n "$COMMAND" ] || { echo "No command constructed" >&2; exit 1; }

TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
RANDOM_TAG=$(python3 - <<'PY'
import secrets
print(secrets.token_hex(3))
PY
)
FAMILY=$(sanitize_label "${LABEL:-$MODE}")
RUN_DIR=$(allocate_run_dir "$FAMILY")

if [ -n "$LABEL" ]; then
  JOB_ID="$(sanitize_label "$LABEL")-${TIMESTAMP}-${RANDOM_TAG}"
else
  JOB_ID="${MODE}-${TIMESTAMP}-${RANDOM_TAG}"
fi

LOG_PATH="$RUN_DIR/job.log"
PID_PATH="$RUN_DIR/job.pid"
META_PATH="$RUN_DIR/job.json"
LEGACY_LOG_PATH="$LEGACY_DIR/${JOB_ID}.log"
LEGACY_PID_PATH="$LEGACY_DIR/${JOB_ID}.pid"
LEGACY_META_PATH="$LEGACY_DIR/${JOB_ID}.json"
STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
STARTED_AT_BERN=$(python3 - <<'PY'
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

print(datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Zurich")).strftime("%Y-%m-%dT%H:%M:%S%z"))
PY
)
TARGET_REPO=$(infer_target_repo)
TARGET_REPO_ROOT="$ROOT_DIR"
TARGET_REPORTS_ROOT="$ROOT_DIR/benchmark"
TARGET_TESTS_ROOT="$ROOT_DIR/tests"
mapfile -t _EXPORT_INFO < <(_infer_export_info "${LABEL:-$MODE}" "$ROOT_DIR")
EXPORT_ROOT="${_EXPORT_INFO[0]:-}"
EXPECTED_EXPORTS_JSON="${_EXPORT_INFO[1]:-[]}"

link_legacy_path "$LOG_PATH" "$LEGACY_LOG_PATH"
link_legacy_path "$PID_PATH" "$LEGACY_PID_PATH"
link_legacy_path "$META_PATH" "$LEGACY_META_PATH"
link_legacy_path "$JOBS_JSON" "$LEGACY_DIR/jobs.json"
link_legacy_path "$JOBS_LOG" "$LEGACY_DIR/jobs.log"

{
  python3 - <<'PY' "$EXPORT_ROOT" "$EXPECTED_EXPORTS_JSON"
import json
import sys

export_root = sys.argv[1]
expected = json.loads(sys.argv[2])
if export_root:
    print(f"# export_root: {export_root}")
if expected:
    print("# expected_exports:")
    for f in expected:
        print(f"#   {f}")
elif export_root:
    print("# expected_exports: (auto-numbered dirs, see export_root)")
print("# " + "-" * 60)
PY
} > "$LOG_PATH"
nohup bash -lc "$COMMAND" >> "$LOG_PATH" 2>&1 &
PID=$!
printf '%s\n' "$PID" > "$PID_PATH"

# --- zombie watchdog --------------------------------------------------------
# A job that stalls producing no output (the "background job stuck for hours,
# nothing happens" failure) is killed automatically: if the log file goes stale
# (no new bytes) for BG_STALE_SECS, or total runtime exceeds BG_MAX_SECS, the
# watchdog terminates the job and its children and appends the reason to the log.
# Tune with BG_STALE_SECS (default 180s) / BG_MAX_SECS (default 1800s);
# disable entirely with BG_WATCHDOG_OFF=1.
if [ "${BG_WATCHDOG_OFF:-0}" != "1" ]; then
  nohup bash -c '
    pid="$1"; log="$2"; stale="$3"; maxs="$4"
    start=$(date +%s)
    while kill -0 "$pid" 2>/dev/null; do
      sleep 15
      now=$(date +%s)
      reason=""
      if [ $((now - start)) -ge "$maxs" ]; then
        reason="max-runtime ${maxs}s exceeded"
      else
        if [ -f "$log" ]; then
          mtime=$(stat -f %m "$log" 2>/dev/null || stat -c %Y "$log" 2>/dev/null || echo "$now")
        else
          mtime="$now"
        fi
        [ $((now - mtime)) -ge "$stale" ] && reason="no output for ${stale}s (stale)"
      fi
      [ -z "$reason" ] && continue
      printf "\n[watchdog] killing job: %s\n" "$reason" >> "$log"
      pkill -P "$pid" 2>/dev/null || true
      kill "$pid" 2>/dev/null || true
      sleep 2
      kill -9 "$pid" 2>/dev/null || true
      break
    done
  ' watchdog "$PID" "$LOG_PATH" "${BG_STALE_SECS:-180}" "${BG_MAX_SECS:-1800}" >/dev/null 2>&1 &
  disown 2>/dev/null || true
fi

write_metadata "$META_PATH" "running" "$JOB_ID" "$PID" "$STARTED_AT" "$STARTED_AT_BERN" "$LABEL" "$MODE" "$LOG_PATH" "$COMMAND" "$TARGET_REPO" "$TARGET_REPO_ROOT" "$TARGET_REPORTS_ROOT" "$TARGET_TESTS_ROOT" "$EXPORT_ROOT" "$EXPECTED_EXPORTS_JSON"

python3 - <<'PY' "$JOBS_JSON" "$JOBS_LOG" "$JOB_ID" "$PID" "$STARTED_AT" "$STARTED_AT_BERN" "$LABEL" "$MODE" "$LOG_PATH" "$COMMAND" "$TARGET_REPO" "$TARGET_REPO_ROOT" "$TARGET_REPORTS_ROOT" "$TARGET_TESTS_ROOT" "$EXPORT_ROOT" "$EXPECTED_EXPORTS_JSON"
import json
import pathlib
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

jobs_path = pathlib.Path(sys.argv[1])
jobs_log_path = pathlib.Path(sys.argv[2])
job_id, pid, started_at, started_at_bern, label, mode, log_path, command, target_repo, target_repo_root, target_reports_root, target_tests_root, export_root, expected_exports = sys.argv[3:]
now_bern = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Zurich")).strftime("%Y-%m-%dT%H:%M:%S%z")

if jobs_path.exists() and jobs_path.read_text(encoding="utf-8").strip():
  try:
    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
  except json.JSONDecodeError:
    jobs = {}
else:
  jobs = {}

if not isinstance(jobs, dict):
  jobs = {}

jobs[job_id] = {
  "job_id": job_id,
  "status": "running",
  "pid": int(pid),
  "started_at": started_at,
  "started_at_bern": started_at_bern,
  "timezone": "Europe/Zurich",
  "label": label,
  "mode": mode,
  "log_path": log_path,
  "command": command,
  "target_repo": target_repo,
  "target_repo_root": target_repo_root,
  "target_reports_root": target_reports_root,
  "target_tests_root": target_tests_root,
  "export_root": export_root,
  "expected_exports": json.loads(expected_exports),
  "updated_at_bern": now_bern,
}

tmp_path = jobs_path.with_suffix(".json.tmp")
tmp_path.write_text(json.dumps(jobs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
tmp_path.replace(jobs_path)

with jobs_log_path.open("a", encoding="utf-8") as handle:
  handle.write(f"{started_at_bern} | {job_id} | {mode} | running | {command}\n")
PY

cat <<EOF
Submitted background job.
  job_id:   $JOB_ID
  pid:      $PID
  mode:     $MODE
  log:      $LOG_PATH
  metadata: $META_PATH
EOF
if [ -n "$EXPORT_ROOT" ]; then
  printf '  exports:  %s\n' "$EXPORT_ROOT"
  python3 - <<'PY' "$EXPECTED_EXPORTS_JSON"
import json, sys
files = json.loads(sys.argv[1])
for f in files:
    print(f"            {f}")
PY
fi
cat <<EOF

Check status with:
  ./scripts/check_pytest_bg.sh --job $JOB_ID
EOF
