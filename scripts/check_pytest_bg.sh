#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

usage() {
  cat <<'EOF'
check_pytest_bg.sh — inspect background pytest/poe jobs

Usage:
  ./scripts/check_pytest_bg.sh
  ./scripts/check_pytest_bg.sh --job JOB_ID
  ./scripts/check_pytest_bg.sh --job JOB_ID --tail 40

Options:
  --job JOB_ID   Show one job instead of all discovered jobs
  --tail N       Print the last N lines from matching log files
EOF
}

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CANONICAL_DIR="$ROOT_DIR/.spectrafit_reports/background-jobs"
LEGACY_DIR="$ROOT_DIR/.pytest_logs"
JOBS_JSON="$CANONICAL_DIR/jobs.json"
JOBS_LOG="$CANONICAL_DIR/jobs.log"
JOB_ID=""
TAIL_LINES=0

status_for_pid() {
  local pid=$1
  if kill -0 "$pid" >/dev/null 2>&1; then
    printf 'running'
  else
    printf 'completed'
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --job)
      JOB_ID=${2:-}
      [ -n "$JOB_ID" ] || { echo "Missing job id after --job" >&2; exit 1; }
      shift 2
      ;;
    --tail)
      TAIL_LINES=${2:-0}
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

[ -d "$CANONICAL_DIR" ] || { echo "No background job archive found under $CANONICAL_DIR"; exit 0; }

shopt -s nullglob
if [ -n "$JOB_ID" ]; then
  META_FILES=("$CANONICAL_DIR"/*/*/job.json)
else
  META_FILES=("$CANONICAL_DIR"/*/*/job.json)
fi

if [ -n "$JOB_ID" ] && [ "${#META_FILES[@]}" -gt 1 ]; then
  FILTERED_META_FILES=()
  for meta in "${META_FILES[@]}"; do
    if python3 - <<'PY' "$meta" "$JOB_ID"
import json
import sys
from pathlib import Path

meta_path = Path(sys.argv[1])
job_id = sys.argv[2]
try:
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)
if payload.get("job_id") == job_id:
    raise SystemExit(0)
raise SystemExit(1)
PY
    then
      FILTERED_META_FILES+=("$meta")
    fi
  done
  META_FILES=("${FILTERED_META_FILES[@]}")
fi

if [ -n "$JOB_ID" ] && [ "${#META_FILES[@]}" -eq 0 ] && [ -e "$LEGACY_DIR/$JOB_ID.json" ]; then
  META_FILES=("$LEGACY_DIR/$JOB_ID.json")
fi

[ "${#META_FILES[@]}" -gt 0 ] || { echo "No matching job metadata found."; exit 0; }

for meta in "${META_FILES[@]}"; do
  python3 - <<'PY' "$meta" "$(status_for_pid "$(python3 - <<'PYPID' "$meta"
import json
import sys
with open(sys.argv[1], encoding='utf-8') as handle:
    data = json.load(handle)
print(data['pid'])
PYPID
)")" "$TAIL_LINES" "$JOBS_JSON" "$JOBS_LOG"
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

meta_path = pathlib.Path(sys.argv[1]).resolve()
status = sys.argv[2]
tail_lines = int(sys.argv[3])
jobs_path = pathlib.Path(sys.argv[4])
jobs_log_path = pathlib.Path(sys.argv[5])

data = json.loads(meta_path.read_text(encoding='utf-8'))
log_path = data.get('log_path') or str(meta_path.with_suffix('.log'))
started_at_bern = data.get('started_at_bern')
if not started_at_bern and data.get('started_at'):
    started_at_bern = datetime.fromisoformat(
        data['started_at'].replace('Z', '+00:00')
    ).astimezone(ZoneInfo('Europe/Zurich')).strftime('%Y-%m-%dT%H:%M:%S%z')
checked_at_bern = datetime.now(timezone.utc).astimezone(ZoneInfo('Europe/Zurich')).strftime('%Y-%m-%dT%H:%M:%S%z')

print(f"job_id: {data['job_id']}")
print(f"status: {status}")
print(f"pid: {data['pid']}")
print(f"mode: {data['mode']}")
if data.get('label'):
    print(f"label: {data['label']}")
print(f"started_at: {data.get('started_at', 'unknown')}")
if started_at_bern:
    print(f"started_at_bern: {started_at_bern}")
print(f"checked_at_bern: {checked_at_bern}")
print(f"log: {log_path}")
print(f"command: {data['command']}")
if data.get('target_repo'):
  print(f"target_repo: {data['target_repo']}")
if data.get('target_repo_root'):
  print(f"target_repo_root: {data['target_repo_root']}")
if data.get('target_reports_root'):
  print(f"target_reports_root: {data['target_reports_root']}")
if data.get('target_tests_root'):
  print(f"target_tests_root: {data['target_tests_root']}")
export_root = data.get('export_root', '')
expected = data.get('expected_exports', [])
if export_root:
    print(f"export_root: {export_root}")
if expected:
    print("expected_exports:")
    for fpath in expected:
        marker = "[found]  " if pathlib.Path(fpath).exists() else "[missing]"
        print(f"  {marker} {fpath}")
elif export_root:
    export_dir = pathlib.Path(export_root)
    if export_dir.exists():
        sub_dirs = sorted(p.name for p in export_dir.iterdir() if p.is_dir())
        print(f"export_dirs: {len(sub_dirs)} dir(s) in {export_dir}")
        for d in sub_dirs[:5]:
            print(f"  {d}/")
        if len(sub_dirs) > 5:
            print(f"  ... and {len(sub_dirs) - 5} more")

if jobs_path.exists() and jobs_path.read_text(encoding='utf-8').strip():
    try:
        jobs = json.loads(jobs_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        jobs = {}
else:
    jobs = {}

if not isinstance(jobs, dict):
    jobs = {}

jobs[data['job_id']] = {
    'job_id': data['job_id'],
    'status': status,
    'pid': int(data['pid']),
    'started_at': data.get('started_at', 'unknown'),
    'started_at_bern': started_at_bern or data.get('started_at', 'unknown'),
    'timezone': 'Europe/Zurich',
    'label': data.get('label', ''),
    'mode': data['mode'],
    'log_path': log_path,
    'command': data['command'],
    'target_repo': data.get('target_repo', ''),
    'target_repo_root': data.get('target_repo_root', ''),
    'target_reports_root': data.get('target_reports_root', ''),
    'target_tests_root': data.get('target_tests_root', ''),
    'export_root': data.get('export_root', ''),
    'expected_exports': data.get('expected_exports', []),
    'updated_at_bern': checked_at_bern,
}

tmp_path = jobs_path.with_suffix('.json.tmp')
tmp_path.write_text(json.dumps(jobs, indent=2, sort_keys=True) + '\n', encoding='utf-8')
tmp_path.replace(jobs_path)

data['status'] = status
data['checked_at_bern'] = checked_at_bern
meta_tmp_path = meta_path.with_suffix('.json.tmp')
meta_tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')
meta_tmp_path.replace(meta_path)

with jobs_log_path.open('a', encoding='utf-8') as handle:
    handle.write(f"{checked_at_bern} | {data['job_id']} | {data['mode']} | {status} | {data['command']}\n")

if tail_lines > 0:
    log_file = pathlib.Path(log_path)
    if log_file.exists():
        print(f"--- tail -n {tail_lines} {log_file} ---")
        subprocess.run(["tail", "-n", str(tail_lines), str(log_file)], check=False)
print()
PY
done
