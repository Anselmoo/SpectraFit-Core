#!/usr/bin/env python3
"""Pydantic-based create validation for .claude/validators/

This validator checks file creation before execution for:
- Path traversal attacks
- Parent directory existence
- File already exists check
- Python syntax compliance (AST validation)
- Rust syntax compliance (basic brace matching)
- Markdown frontmatter compliance (for instructions/agents)

REQUIREMENTS:
- Python 3.13+
- Pydantic v2 (must activate .venv: source .venv/bin/activate)
- Run with: uv run python .claude/validators/pydantic_create.py <path> <content>
"""

import ast
import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class CreateValidationRequest(BaseModel):
    """Create tool input validation schema"""

    path: str = Field(..., description="File path to create")
    content: str = Field(..., description="Initial file content")

    @field_validator("path")
    @classmethod
    def validate_no_traversal(cls, v: str) -> str:
        """Deny path traversal attacks"""
        if ".." in v or v.startswith("/"):
            raise ValueError(f"Path traversal detected: {v}")
        return v


class PythonFileValidation(BaseModel):
    """Python file syntax validation"""

    path: str = Field(..., pattern=r".*\.py$")
    content: str

    @field_validator("content")
    @classmethod
    def validate_python_syntax(cls, v: str) -> str:
        """Validate Python AST syntax"""
        if not v.strip():
            return v  # Empty files are OK

        try:
            ast.parse(v)
        except SyntaxError as e:
            raise ValueError(f"Python syntax error at line {e.lineno}: {e.msg}")

        return v


class RustFileValidation(BaseModel):
    """Rust file basic validation"""

    path: str = Field(..., pattern=r".*\.rs$")
    content: str

    @field_validator("content")
    @classmethod
    def validate_rust_syntax_basic(cls, v: str) -> str:
        """Basic Rust brace matching (not full parser)"""
        if not v.strip():
            return v

        # Simple brace counting
        braces = v.count("{") - v.count("}")
        parens = v.count("(") - v.count(")")
        brackets = v.count("[") - v.count("]")

        if braces != 0 or parens != 0 or brackets != 0:
            raise ValueError(
                f"Rust syntax error: unbalanced braces/parens/brackets "
                f"(braces: {braces}, parens: {parens}, brackets: {brackets})"
            )

        return v


class MarkdownFrontmatterValidation(BaseModel):
    """Markdown file frontmatter validation (for instructions/agents)"""

    path: str = Field(..., pattern=r".*\.md$")
    content: str

    @field_validator("content")
    @classmethod
    def validate_frontmatter(cls, v: str) -> str:
        """Check for valid YAML frontmatter if present"""
        if not v.startswith("---"):
            return v  # No frontmatter required

        # Simple check: must have closing ---
        lines = v.split("\n")
        if len(lines) < 3:
            raise ValueError("Markdown frontmatter incomplete: missing closing ---")

        # Find closing frontmatter marker
        closing_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                closing_idx = i
                break

        if closing_idx is None:
            raise ValueError("Markdown: unclosed frontmatter (missing closing ---)")

        return v


class CreateValidation(BaseModel):
    """Main create validation orchestrator"""

    path: str = Field(..., description="File path")
    content: str = Field(..., description="Initial content")

    @field_validator("path")
    @classmethod
    def check_path_security(cls, v: str) -> str:
        """Step 1: Security checks"""
        if ".." in v or v.startswith("/"):
            raise ValueError(f"Path traversal detected: {v}")
        return v

    def validate_context_specific(self) -> tuple[bool, str]:
        """Step 2-3: Context-specific validation based on file type"""
        try:
            # Check parent directory can be created
            path_obj = Path(self.path)
            parent = path_obj.parent

            # Parent must exist or be creatable
            if parent.exists() and not parent.is_dir():
                return False, f"Parent path exists but is not a directory: {parent}"

            # File must not already exist
            if path_obj.exists():
                return False, f"File already exists: {self.path}"

            # Python file: validate syntax
            if self.path.endswith(".py"):
                try:
                    PythonFileValidation(path=self.path, content=self.content)
                    return True, "Python syntax valid"
                except ValueError as e:
                    return False, str(e)

            # Rust file: validate syntax
            elif self.path.endswith(".rs"):
                try:
                    RustFileValidation(path=self.path, content=self.content)
                    return True, "Rust syntax valid"
                except ValueError as e:
                    return False, str(e)

            # Markdown: validate frontmatter
            elif self.path.endswith(".md"):
                try:
                    MarkdownFrontmatterValidation(path=self.path, content=self.content)
                    return True, "Markdown frontmatter valid"
                except ValueError as e:
                    return False, str(e)

            # Benchmark evidence index: validate required performance dimensions
            elif self.path.endswith("results_index.json"):
                try:
                    payload = json.loads(self.content)
                except json.JSONDecodeError as exc:
                    return False, f"Benchmark evidence JSON invalid: {exc}"

                scenarios = payload.get("scenarios")
                if not isinstance(scenarios, list) or not scenarios:
                    return False, (
                        "Benchmark evidence invalid: results_index.json must include "
                        "a non-empty 'scenarios' array."
                    )

                has_short = any(
                    isinstance(item, dict) and item.get("dataset_scale") == "short"
                    for item in scenarios
                )
                has_large = any(
                    isinstance(item, dict) and item.get("dataset_scale") == "large"
                    for item in scenarios
                )
                has_cold_hot = any(
                    isinstance(item, dict) and item.get("timing_mode") == "cold_and_hot"
                    for item in scenarios
                )
                has_hot_speedup = any(
                    isinstance(item, dict)
                    and item.get("speedup_lmfit_over_spectrafit_hot") is not None
                    for item in scenarios
                )
                has_cold_speedup_for_cold_hot = all(
                    not (
                        isinstance(item, dict)
                        and item.get("timing_mode") == "cold_and_hot"
                    )
                    or item.get("speedup_lmfit_over_spectrafit_cold") is not None
                    for item in scenarios
                )

                if not has_short or not has_large:
                    return False, (
                        "Benchmark evidence invalid: include both short and large "
                        "dataset_scale scenarios."
                    )
                if not has_cold_hot:
                    return False, (
                        "Benchmark evidence invalid: include at least one "
                        "cold_and_hot timing_mode scenario."
                    )
                if not has_hot_speedup:
                    return False, (
                        "Benchmark evidence invalid: missing "
                        "speedup_lmfit_over_spectrafit_hot values."
                    )
                if not has_cold_speedup_for_cold_hot:
                    return False, (
                        "Benchmark evidence invalid: cold_and_hot scenarios must "
                        "include speedup_lmfit_over_spectrafit_cold."
                    )

                return True, "Benchmark evidence validation passed"

            elif self.path.endswith("results_feedback.json"):
                try:
                    payload = json.loads(self.content)
                except json.JSONDecodeError as exc:
                    return False, f"Benchmark feedback JSON invalid: {exc}"

                gates = payload.get("gates")
                if not isinstance(gates, dict):
                    return False, (
                        "Benchmark feedback invalid: results_feedback.json must "
                        "include object field 'gates'."
                    )

                required_gate_keys = {
                    "short_hot_speedup_gt_1",
                    "large_hot_speedup_gt_1",
                    "cold_speedup_coverage_for_cold_and_hot",
                    "overall",
                }
                missing = required_gate_keys - set(gates.keys())
                if missing:
                    return False, (
                        "Benchmark feedback invalid: missing required gates: "
                        f"{', '.join(sorted(missing))}."
                    )

                if not all(isinstance(gates[key], bool) for key in required_gate_keys):
                    return False, (
                        "Benchmark feedback invalid: all required gate values "
                        "must be booleans."
                    )

                recommendations = payload.get("recommendations")
                if not isinstance(recommendations, list) or not recommendations:
                    return False, (
                        "Benchmark feedback invalid: recommendations must be a "
                        "non-empty array."
                    )

                if gates.get("overall") is not True:
                    return False, (
                        "Benchmark feedback invalid: overall gate must be true "
                        "for merge-ready performance evidence."
                    )

                return True, "Benchmark feedback validation passed"

            return True, "File creation checks passed"

        except Exception as e:
            return False, f"Validation error: {str(e)}"


def validate_create(path: str, content: str) -> dict:
    """Main entry point for create validation

    Returns JSON:
    {
      "decision": "allow" | "deny",
      "reason": "explanation",
      "violations": ["violation1", "violation2"]
    }
    """
    violations = []

    try:
        # Step 1: Basic validation
        CreateValidationRequest(path=path, content=content)

        # Step 2: Context-specific validation
        validator = CreateValidation(path=path, content=content)
        passed, reason = validator.validate_context_specific()

        if not passed:
            violations.append(reason)
            return {"decision": "deny", "reason": reason, "violations": violations}

        return {
            "decision": "allow",
            "reason": "File creation passed all validation checks",
            "violations": [],
        }

    except ValueError as e:
        violations.append(str(e))
        return {"decision": "deny", "reason": str(e), "violations": violations}

    except Exception as e:
        return {
            "decision": "deny",
            "reason": f"Validation error: {str(e)}",
            "violations": [str(e)],
        }


if __name__ == "__main__":
    """
    CLI interface: pydantic_create.py <path> <content>
    
    Outputs JSON to stdout
    Exit 0: allow (decision=allow)
    Exit 1: deny (decision=deny)
    """

    if len(sys.argv) < 3:
        result = {
            "decision": "deny",
            "reason": "Usage: pydantic_create.py <path> <content>",
            "violations": ["Missing arguments"],
        }
        print(json.dumps(result))
        sys.exit(1)

    path = sys.argv[1]
    content = sys.argv[2]

    result = validate_create(path, content)
    print(json.dumps(result))

    sys.exit(0 if result["decision"] == "allow" else 1)
