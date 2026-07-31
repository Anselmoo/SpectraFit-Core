#!/usr/bin/env python3
"""Pydantic-based bash validation for .claude/validators/

This validator checks bash commands before execution for:
- Dangerous patterns (rm -rf, git push --force, sudo, fork bombs)
- Command injection attempts
- Long-running operations
- Safe commands allowed with logging

REQUIREMENTS:
- Python 3.13+
- Pydantic v2 (must activate .venv: source .venv/bin/activate)
- Run with: uv run python .claude/validators/pydantic_bash.py "command"
"""

import json
import re
import sys

from pydantic import BaseModel, Field, field_validator


# Patterns that are always denied (catastrophic risk)
DENY_PATTERNS: list[str] = [
    r"\brm\s+-rf\b",  # rm -rf (recursive force delete)
    r"\bgit\s+push\s+--force\b",  # git push --force (force push)
    r"\bsudo\b",  # sudo (privilege escalation)
    r":\(\)\s*{.*:\|:&\s*};:",  # Fork bomb
    r"\|\s*sh\b",  # pipe to sh (code injection)
    r"`.*`",  # Backtick command substitution (risky)
    r"\$\(.*\)",  # Command substitution (risky if unvalidated)
]

# Patterns that are warned about (side effects, but not catastrophic)
WARN_PATTERNS: list[tuple[str, str]] = [
    (r"\b(curl|wget|python|node)\b.*https?://", "Network operation"),
    (r"sleep\s+\d{3,}", "Long-running sleep"),
    (r"while.*:\s*do", "Infinite loop"),
    (r"\bkill\s+", "Process termination"),
]


class BashCommandValidation(BaseModel):
    """Bash command validation schema"""

    command: str = Field(..., description="Bash command to execute")

    @field_validator("command")
    @classmethod
    def validate_command_safety(cls, v: str) -> str:
        """Check for dangerous patterns"""
        if not v.strip():
            raise ValueError("Empty command")

        # Check deny patterns
        for pattern in DENY_PATTERNS:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError(
                    f"Dangerous pattern detected: {pattern}. "
                    f"Command blocked for safety."
                )

        return v


class BashCommandAnalysis(BaseModel):
    """Detailed bash command analysis"""

    command: str

    def analyze_risks(self) -> tuple[str, list[str], list[str]]:
        """Analyze command for risks

        Returns: (severity, warnings, info)
        - severity: "safe" | "risky" | "denied"
        - warnings: list of warning messages
        - info: list of informational messages
        """
        warnings: list[str] = []
        info: list[str] = []

        # Check for denied patterns
        for pattern in DENY_PATTERNS:
            if re.search(pattern, self.command, re.IGNORECASE):
                return "denied", [f"Denied: {pattern}"], []

        # Check for warning patterns
        for pattern, description in WARN_PATTERNS:
            if re.search(pattern, self.command, re.IGNORECASE):
                warnings.append(f"{description}: {pattern}")

        # Estimate execution time for long commands
        if any(
            cmd in self.command
            for cmd in [
                "cargo build",
                "npm install",
                "pip install",
                "uv run",
                "pytest",
                "benchmark",
            ]
        ):
            warnings.append("This command may take several minutes to complete")

        # Check for common safe patterns
        safe_patterns = [
            "echo",
            "ls",
            "pwd",
            "cd",
            "cat",
            "grep",
            "git add",
            "git commit",
            "git status",
            "python -c",
            "python script.py",
        ]
        if any(cmd in self.command for cmd in safe_patterns):
            info.append("Command appears safe (common utility)")

        severity = "safe"
        if warnings:
            severity = "risky"

        return severity, warnings, info


def validate_bash(command: str) -> dict:
    """Main entry point for bash validation

    Returns JSON:
    {
      "decision": "allow" | "deny" | "ask",
      "reason": "explanation",
      "severity": "safe" | "risky" | "denied",
      "violations": ["violation1"],
      "warnings": ["warning1"],
      "info": ["info1"]
    }
    """
    warnings: list[str] = []
    info: list[str] = []
    violations: list[str] = []

    try:
        # Step 1: Validate command
        validation = BashCommandValidation(command=command)

        # Step 2: Analyze risks
        analysis = BashCommandAnalysis(command=command)
        severity, warnings, info = analysis.analyze_risks()

        if severity == "denied":
            violations.extend(warnings)
            return {
                "decision": "deny",
                "reason": f"Command blocked: {warnings[0] if warnings else 'dangerous pattern'}",
                "severity": "denied",
                "violations": violations,
                "warnings": [],
                "info": [],
            }

        if severity == "risky":
            return {
                "decision": "ask",
                "reason": f"Command has potential risks: {'; '.join(warnings[:2])}",
                "severity": "risky",
                "violations": [],
                "warnings": warnings,
                "info": info,
            }

        # Safe command
        return {
            "decision": "allow",
            "reason": "Command passed safety validation",
            "severity": "safe",
            "violations": [],
            "warnings": [],
            "info": info,
        }

    except ValueError as e:
        violations.append(str(e))
        return {
            "decision": "deny",
            "reason": str(e),
            "severity": "denied",
            "violations": violations,
            "warnings": [],
            "info": [],
        }

    except Exception as e:
        return {
            "decision": "deny",
            "reason": f"Validation error: {str(e)}",
            "severity": "denied",
            "violations": [str(e)],
            "warnings": [],
            "info": [],
        }


if __name__ == "__main__":
    """
    CLI interface: pydantic_bash.py <command>
    
    Outputs JSON to stdout
    Exit 0: allow (decision=allow)
    Exit 1: deny (decision=deny)
    Exit 2: ask (decision=ask - requires confirmation)
    """

    if len(sys.argv) < 2:
        result = {
            "decision": "deny",
            "reason": "Usage: pydantic_bash.py <command>",
            "severity": "denied",
            "violations": ["Missing command argument"],
            "warnings": [],
            "info": [],
        }
        print(json.dumps(result))
        sys.exit(1)

    command = sys.argv[1]

    result = validate_bash(command)
    print(json.dumps(result))

    if result["decision"] == "allow":
        sys.exit(0)
    elif result["decision"] == "ask":
        sys.exit(2)  # Requires confirmation
    else:
        sys.exit(1)  # Denied
