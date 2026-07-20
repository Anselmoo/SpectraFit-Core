#!/usr/bin/env python3
"""Hook helper for cloud batch pytest workflows.

This hook keeps long-running pytest/poe workloads on the detached job path and
injects compact status summaries from `.pytest_logs/*.json` and
`.spectrafit_reports/*/feedback.json`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

HEAVY_PATTERNS = (
    "uv run pytest",
    "python -m pytest",
    "pytest tests/speedboat",
    "pytest tests/quick_validation",
    "uv run poe benchmark",
    "uv run poe quick_validation",
    "poe benchmark",
    "poe quick_validation",
)

SAFE_BG_MARKERS = (
    "./scripts/run_pytest_bg.sh",
    "scripts/run_pytest_bg.sh",
    "./scripts/run_speedboat_bg.sh",
    "scripts/run_speedboat_bg.sh",
    "./scripts/check_pytest_bg.sh",
    "scripts/check_pytest_bg.sh",
)

BENCHMARK_ARTIFACT_PATTERNS = (
    "benchmark/report.html",
    "benchmark/results.json",
    "benchmark/",
)


def emit(payload: dict[str, Any]) -> int:
    """Print a JSON hook response and return success."""
    print(json.dumps(payload))
    return 0


def load_stdin() -> dict[str, Any]:
    """Read and parse the hook payload from standard input."""
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


def workspace_root(payload: dict[str, Any]) -> Path:
    """Resolve the workspace root from the hook payload or repository path."""
    cwd = payload.get("cwd")
    if cwd:
        return Path(cwd)
    return Path(__file__).resolve().parents[2]


def process_running(pid: int) -> bool:
    """Return ``True`` when the given process id is still alive."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def load_job_metadata(root: Path) -> list[dict[str, Any]]:
    """Load background-job metadata from the canonical archive or legacy mirror."""
    canonical_root = root / ".spectrafit_reports" / "background-jobs"
    legacy_root = root / ".pytest_logs"
    jobs_by_id: dict[str, dict[str, Any]] = {}

    def ingest(meta_paths: list[Path]) -> None:
        for meta_path in sorted(meta_paths):
            if meta_path.name == "jobs.json":
                continue
            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            job_id = str(payload.get("job_id") or meta_path.stem)
            pid = int(payload.get("pid", -1))
            payload["status"] = (
                "running" if pid > 0 and process_running(pid) else "completed"
            )
            payload["meta_path"] = str(meta_path)
            jobs_by_id.setdefault(job_id, payload)

    if canonical_root.exists():
        ingest(list(canonical_root.glob("*/*/job.json")))
    if not jobs_by_id and legacy_root.exists():
        ingest(list(legacy_root.glob("*.json")))

    jobs = list(jobs_by_id.values())
    jobs.sort(key=lambda item: item.get("started_at", ""), reverse=True)
    return jobs


def summarize_log(log_path: str, lines: int = 8) -> str:
    """Return the tail of a log file as a compact single string."""
    path = Path(log_path)
    if not path.exists():
        return ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    tail = content[-lines:]
    return "\n".join(tail).strip()


def find_latest_feedback(root: Path) -> dict[str, Any] | None:
    """Load the newest numbered feedback.json payload from benchmark reports."""
    base = root / ".spectrafit_reports"
    if not base.exists():
        return None
    candidates = sorted(
        (path for path in base.glob("*/feedback.json") if path.parent.name.isdigit()),
        key=lambda item: item.parent.name,
        reverse=True,
    )
    for candidate in candidates:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        payload["_path"] = str(candidate)
        return payload
    return None


def compact_job_summary(root: Path) -> str:
    """Build a short human-readable summary of background jobs and feedback."""
    jobs = load_job_metadata(root)
    if not jobs:
        return "No background pytest jobs found under .spectrafit_reports/background-jobs/."

    running = [job for job in jobs if job["status"] == "running"]
    completed = [job for job in jobs if job["status"] == "completed"]
    parts = [
        f"background jobs: {len(running)} running, {len(completed)} completed",
    ]

    for job in jobs[:3]:
        line = (
            f"- {job.get('job_id')} [{job.get('status')}]"
            f" mode={job.get('mode')} label={job.get('label') or '-'}"
        )
        tail = summarize_log(job.get("log_path", ""), lines=3)
        if tail:
            cleaned = tail.replace("\n", " | ")
            line += f" tail={cleaned[:280]}"
        parts.append(line)

    feedback = find_latest_feedback(root)
    if feedback:
        gates = feedback.get("gates") or {}
        overall = gates.get("overall")
        rec_count = len(feedback.get("recommendations") or [])
        parts.append(
            f"latest feedback: overall={overall} recommendations={rec_count} path={feedback.get('_path')}"
        )
    return "\n".join(parts)


def maybe_gate_terminal_command(
    payload: dict[str, Any], root: Path
) -> dict[str, Any] | None:
    """Gate dangerous terminal commands and encourage detached job execution."""
    if payload.get("tool_name") != "run_in_terminal":
        return None

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "")
    lowered = command.lower()

    if any(marker in command for marker in SAFE_BG_MARKERS):
        return None

    if "git add" in lowered and any(
        pattern in lowered for pattern in BENCHMARK_ARTIFACT_PATTERNS
    ):
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Generated benchmark artifacts must stay out of git. Keep benchmark/*.json, *.html, and *.pdf as runtime outputs only.",
                "additionalContext": "Use .spectrafit_reports/ or external artifacts for large reports, and keep benchmark outputs ignored.",
            },
            "systemMessage": "Blocked staging of generated benchmark artifacts.",
        }

    if any(pattern in lowered for pattern in HEAVY_PATTERNS):
        summary = compact_job_summary(root)
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": "Heavy pytest/poe workloads on this cloud resource should normally run through ./scripts/run_pytest_bg.sh so they survive SSH disconnects and preserve JSON/log metadata.",
                "additionalContext": summary,
            },
            "systemMessage": "Consider using ./scripts/run_pytest_bg.sh for long-running pytest/poe jobs.",
        }
    return None


def post_tool_context(payload: dict[str, Any], root: Path) -> dict[str, Any] | None:
    """Attach post-tool context for background job commands."""
    if payload.get("tool_name") != "run_in_terminal":
        return None
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "")
    if not any(marker in command for marker in SAFE_BG_MARKERS + HEAVY_PATTERNS):
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": compact_job_summary(root),
        }
    }


def session_start_context(root: Path) -> dict[str, Any]:
    """Return the startup context banner for the background-job workflow."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                "Cloud batch workflow active for spectrafit-core. "
                "Use ./scripts/run_pytest_bg.sh for heavy pytest/poe runs and "
                "./scripts/check_pytest_bg.sh to inspect jobs.\n"
                + compact_job_summary(root)
            ),
        }
    }


def main() -> int:
    """Dispatch the hook event and emit the corresponding JSON response."""
    payload = load_stdin()
    event = payload.get("hookEventName")
    root = workspace_root(payload)

    if event == "SessionStart":
        return emit(session_start_context(root))
    if event == "PreToolUse":
        result = maybe_gate_terminal_command(payload, root)
        return emit(result or {"continue": True})
    if event == "PostToolUse":
        result = post_tool_context(payload, root)
        return emit(result or {"continue": True})
    return emit({"continue": True})


if __name__ == "__main__":
    raise SystemExit(main())
