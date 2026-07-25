#!/usr/bin/env python3
"""Self-healing checks for hooks, skills, agents, and instructions.

This command performs hybrid drift detection:
1. structural validity checks, and
2. cross-reference contract checks.

In ``fix-safe`` mode it applies deterministic low-risk fixes only.
Reports are written to ``.spectrafit_reports/self-heal/<run-id>/``.
"""

from __future__ import annotations

import argparse
import json
import re
import stat
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


TARGET_PREFIXES: tuple[str, ...] = (
    ".claude/hooks/",
    ".claude/settings.json",
    ".claude/agents/",
    ".github/skills/",
    ".github/instructions/",
)

VERB_PREFIXES: tuple[str, ...] = (
    "Analyzes",
    "Generates",
    "Validates",
    "Implements",
    "Builds",
    "Routes",
    "Maintains",
    "Creates",
    "Designs",
    "Extends",
    "Audits",
    "Orchestrates",
)


@dataclass(slots=True)
class Finding:
    """One drift finding from a self-heal pass."""

    surface: str
    path: str
    code: str
    severity: str
    message: str
    safe_fixable: bool = False
    fixed: bool = False
    details: dict[str, Any] | None = None


def _as_posix_path(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def _is_target_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in TARGET_PREFIXES)


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for nested in value.values():
            yield from _iter_strings(nested)
        return
    if isinstance(value, list):
        for nested in value:
            yield from _iter_strings(nested)


def _extract_hook_refs(text: str) -> set[str]:
    return set(re.findall(r"\.claude/hooks/([A-Za-z0-9._-]+\.sh)", text))


def _parse_frontmatter(text: str) -> tuple[dict[str, str] | None, str | None]:
    if not text.startswith("---\n"):
        return None, "missing_frontmatter"
    end = text.find("\n---\n", 4)
    if end < 0:
        return None, "unclosed_frontmatter"
    body = text[4:end]
    data: dict[str, str] = {}
    for line in body.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data, None


def _validate_settings_and_hook_contracts(
    repo_root: Path,
    findings: list[Finding],
) -> None:
    settings_path = repo_root / ".claude/settings.json"
    precommit_path = repo_root / ".pre-commit-config.yaml"
    hooks_dir = repo_root / ".claude/hooks"

    settings_refs: set[str] = set()
    if settings_path.exists():
        try:
            payload = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(
                Finding(
                    surface="hooks",
                    path=_as_posix_path(settings_path.relative_to(repo_root)),
                    code="settings_invalid_json",
                    severity="error",
                    message=f".claude/settings.json is invalid JSON: {exc}",
                )
            )
            payload = None
        if payload is not None:
            for text in _iter_strings(payload):
                settings_refs.update(_extract_hook_refs(text))
    else:
        findings.append(
            Finding(
                surface="hooks",
                path=".claude/settings.json",
                code="settings_missing",
                severity="error",
                message=".claude/settings.json is missing.",
            )
        )

    precommit_refs: set[str] = set()
    if precommit_path.exists():
        precommit_refs = _extract_hook_refs(precommit_path.read_text(encoding="utf-8"))

    referenced = settings_refs | precommit_refs
    for hook_file in sorted(referenced):
        hook_path = hooks_dir / hook_file
        if not hook_path.exists():
            findings.append(
                Finding(
                    surface="hooks",
                    path=f".claude/hooks/{hook_file}",
                    code="hook_reference_missing",
                    severity="error",
                    message=f"Referenced hook script is missing: .claude/hooks/{hook_file}",
                    details={"referenced_by": ["settings.json/pre-commit"]},
                )
            )

    if hooks_dir.exists():
        all_hooks = sorted(hooks_dir.glob("*.sh"))
        for hook in all_hooks:
            rel_hook = _as_posix_path(hook.relative_to(repo_root))
            if hook.name not in referenced:
                findings.append(
                    Finding(
                        surface="hooks",
                        path=rel_hook,
                        code="hook_unreferenced",
                        severity="warning",
                        message=f"Hook script is not referenced by settings/pre-commit: {rel_hook}",
                    )
                )
            mode = hook.stat().st_mode
            if not (mode & stat.S_IXUSR):
                findings.append(
                    Finding(
                        surface="hooks",
                        path=rel_hook,
                        code="hook_not_executable",
                        severity="error",
                        message=f"Hook script is not executable: {rel_hook}",
                        safe_fixable=True,
                    )
                )
            first_line = hook.read_text(encoding="utf-8", errors="ignore").splitlines()
            if not first_line or not first_line[0].startswith("#!"):
                findings.append(
                    Finding(
                        surface="hooks",
                        path=rel_hook,
                        code="hook_missing_shebang",
                        severity="warning",
                        message=f"Hook script has no shebang: {rel_hook}",
                    )
                )


def _validate_instruction_file(
    repo_root: Path, rel_path: str, findings: list[Finding]
) -> None:
    path = repo_root / rel_path
    text = path.read_text(encoding="utf-8")
    frontmatter, error = _parse_frontmatter(text)
    if error:
        findings.append(
            Finding(
                surface="instructions",
                path=rel_path,
                code=error,
                severity="error",
                message=f"Instruction file frontmatter issue: {error}",
            )
        )
        return
    assert frontmatter is not None
    for key in ("applyTo", "description"):
        if key not in frontmatter or not frontmatter[key]:
            findings.append(
                Finding(
                    surface="instructions",
                    path=rel_path,
                    code=f"instruction_missing_{key}",
                    severity="error",
                    message=f"Instruction frontmatter missing '{key}'.",
                )
            )


def _validate_agent_file(
    repo_root: Path, rel_path: str, findings: list[Finding]
) -> None:
    path = repo_root / rel_path
    text = path.read_text(encoding="utf-8")
    frontmatter, error = _parse_frontmatter(text)
    if error:
        findings.append(
            Finding(
                surface="agents",
                path=rel_path,
                code=error,
                severity="error",
                message=f"Agent file frontmatter issue: {error}",
            )
        )
        return
    assert frontmatter is not None
    description = frontmatter.get("description", "")
    if not description:
        findings.append(
            Finding(
                surface="agents",
                path=rel_path,
                code="agent_missing_description",
                severity="error",
                message="Agent frontmatter is missing description.",
            )
        )
    else:
        if "Use when" not in description:
            findings.append(
                Finding(
                    surface="agents",
                    path=rel_path,
                    code="agent_description_missing_trigger",
                    severity="warning",
                    message="Agent description should include 'Use when…' trigger phrase.",
                )
            )
        if not any(description.startswith(prefix) for prefix in VERB_PREFIXES):
            findings.append(
                Finding(
                    surface="agents",
                    path=rel_path,
                    code="agent_description_not_verb",
                    severity="warning",
                    message="Agent description should start with a verb (e.g., Analyzes/Generates/Validates).",
                )
            )
    lowered = text.lower()
    if "## non-goals" not in lowered and "## out of scope" not in lowered:
        findings.append(
            Finding(
                surface="agents",
                path=rel_path,
                code="agent_non_goals_missing",
                severity="warning",
                message="Agent should document non-goals/out-of-scope section.",
            )
        )
    if (
        "## termination criteria" not in lowered
        and "## completion criteria" not in lowered
    ):
        findings.append(
            Finding(
                surface="agents",
                path=rel_path,
                code="agent_termination_missing",
                severity="warning",
                message="Agent should document measurable termination/completion criteria.",
            )
        )


def _validate_skill_file(
    repo_root: Path, rel_path: str, findings: list[Finding]
) -> None:
    path = repo_root / rel_path
    text = path.read_text(encoding="utf-8")
    required_sections = (
        "## Workflow",
        "## Conventions",
        "## Anti-patterns",
        "## Output format",
    )
    for section in required_sections:
        if section.lower() not in text.lower():
            findings.append(
                Finding(
                    surface="skills",
                    path=rel_path,
                    code="skill_section_missing",
                    severity="warning",
                    message=f"SKILL.md should include section: {section}",
                    details={"missing_section": section},
                )
            )


def _apply_safe_fix(repo_root: Path, finding: Finding) -> bool:
    if finding.code == "hook_not_executable":
        path = repo_root / finding.path
        if path.exists():
            mode = path.stat().st_mode
            path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP)
            return True
    return False


def _write_report(
    repo_root: Path,
    report_root: Path,
    mode: str,
    findings: list[Finding],
    exit_code: int,
) -> Path:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = report_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    as_json = [asdict(item) for item in findings]
    fixed = [item for item in as_json if item["fixed"]]
    remaining = [item for item in as_json if not item["fixed"]]
    errors_remaining = [item for item in remaining if item["severity"] == "error"]
    warnings_remaining = [item for item in remaining if item["severity"] == "warning"]

    summary = {
        "mode": mode,
        "generated_at": datetime.now(UTC).isoformat(),
        "total_findings": len(findings),
        "fixed_count": len(fixed),
        "remaining_error_count": len(errors_remaining),
        "remaining_warning_count": len(warnings_remaining),
        "exit_code": exit_code,
    }

    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    (run_dir / "fixes_applied.json").write_text(
        json.dumps(fixed, indent=2, sort_keys=True), encoding="utf-8"
    )
    (run_dir / "remaining_violations.json").write_text(
        json.dumps(remaining, indent=2, sort_keys=True), encoding="utf-8"
    )
    return run_dir


def _discover_targets(repo_root: Path, provided: list[str]) -> list[str]:
    if provided:
        normalized = sorted({_as_posix_path(Path(path)) for path in provided})
        return [path for path in normalized if _is_target_path(path)]

    discovered: list[str] = []
    for prefix in (
        ".claude/hooks",
        ".claude/agents",
        ".github/skills",
        ".github/instructions",
    ):
        root = repo_root / prefix
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                rel = _as_posix_path(path.relative_to(repo_root))
                if _is_target_path(rel):
                    discovered.append(rel)
    settings_path = repo_root / ".claude/settings.json"
    if settings_path.exists():
        discovered.append(".claude/settings.json")
    return sorted(set(discovered))


def run(mode: str, report_root: Path, paths: list[str], fail_on_fixes: bool) -> int:
    """Run self-heal checks/fixes and return process exit code."""
    repo_root = Path.cwd()
    findings: list[Finding] = []
    selected = _discover_targets(repo_root, paths)

    should_check_hooks_contracts = not paths or any(
        path.startswith(".claude/hooks/") or path == ".claude/settings.json"
        for path in selected
    )
    if should_check_hooks_contracts:
        _validate_settings_and_hook_contracts(repo_root, findings)

    for rel_path in selected:
        if rel_path.startswith(".github/instructions/") and rel_path.endswith(
            ".instructions.md"
        ):
            _validate_instruction_file(repo_root, rel_path, findings)
        elif rel_path.startswith(".claude/agents/") and rel_path.endswith(".agent.md"):
            _validate_agent_file(repo_root, rel_path, findings)
        elif rel_path.startswith(".github/skills/") and rel_path.endswith("/SKILL.md"):
            _validate_skill_file(repo_root, rel_path, findings)

    if mode == "fix-safe":
        for finding in findings:
            if finding.safe_fixable and _apply_safe_fix(repo_root, finding):
                finding.fixed = True

    remaining_errors = [
        item for item in findings if item.severity == "error" and not item.fixed
    ]
    applied_fixes = [item for item in findings if item.fixed]
    exit_code = 0
    if remaining_errors:
        exit_code = 1
    elif mode == "fix-safe" and fail_on_fixes and applied_fixes:
        exit_code = 1

    output_dir = _write_report(repo_root, report_root, mode, findings, exit_code)
    print(
        "[self-heal] "
        f"mode={mode} findings={len(findings)} "
        f"fixed={len(applied_fixes)} errors={len(remaining_errors)} "
        f"report={_as_posix_path(output_dir.relative_to(repo_root))}"
    )
    return exit_code


def main() -> int:
    """Parse CLI args and execute self-heal checks."""
    parser = argparse.ArgumentParser(
        description="Self-healing automation checks for repo metadata surfaces."
    )
    parser.add_argument(
        "--mode",
        choices=("check", "fix-safe"),
        default="check",
        help="check: report-only, fix-safe: apply deterministic low-risk fixes.",
    )
    parser.add_argument(
        "--report-root",
        default=".spectrafit_reports/self-heal",
        help="Report root directory.",
    )
    parser.add_argument(
        "--fail-on-fixes",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="In fix-safe mode, return non-zero when fixes were applied.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional changed file paths. If omitted, scans the full target surfaces.",
    )
    args = parser.parse_args()
    report_root = Path(args.report_root)
    if not report_root.is_absolute():
        report_root = Path.cwd() / report_root
    return run(args.mode, report_root, args.paths, args.fail_on_fixes)


if __name__ == "__main__":
    raise SystemExit(main())
