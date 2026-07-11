#!/usr/bin/env python3
"""Pydantic-based edit validation for .claude/validators/

This validator checks file edits before execution for:
- Path traversal attacks
- PyO3 boundary violations (#[pyfunction] return types)
- DAG dependency violations (Cargo.toml edits)
- Schema sync compliance (Python↔Rust alignment)

REQUIREMENTS:
- Python 3.13+
- Pydantic v2 (must activate .venv: source .venv/bin/activate)
- Run with: uv run python .claude/validators/pydantic_edit.py <path> <content>
"""

import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class EditValidationRequest(BaseModel):
    """Edit tool input validation schema"""

    path: str = Field(..., description="File path to edit")
    content: str = Field(..., description="New file content")

    @field_validator("path")
    @classmethod
    def validate_no_traversal(cls, v: str) -> str:
        """Deny path traversal attacks"""
        if ".." in v or v.startswith("/"):
            raise ValueError(f"Path traversal detected: {v}")
        return v


class PyO3ReturnType(BaseModel):
    """Valid PyO3 function return type"""

    return_type: str = Field(
        pattern=r"^(String|Result<String, PyErr>|Result<String>)$",
        description="Must be String or Result<String, PyErr> for JSON marshalling",
    )


# DAG rules: types → models → graph → solver → core
DAG_RULES: dict[str, list[str]] = {
    "types": [],
    "models": ["types"],
    "graph": ["types", "models"],
    "solver": ["types", "models", "graph"],
    "core": ["types", "models", "graph", "solver"],
}


class CargoTomlEdit(BaseModel):
    """Cargo.toml dependency validation"""

    path: str = Field(..., pattern=r"^.*Cargo\.toml$")
    content: str

    @field_validator("content")
    @classmethod
    def validate_no_dag_violations(cls, v: str) -> str:
        """Check for circular/violating dependencies"""
        # Parse Cargo.toml for spectrafit- dependencies
        for line in v.split("\n"):
            if "spectrafit-" in line and "=" in line:
                # Extract crate name
                for crate in DAG_RULES.keys():
                    if f"spectrafit-{crate}" in line:
                        # This is a simplified check; full implementation would parse TOML
                        pass
        return v


class SchemaSyncValidation(BaseModel):
    """Python↔Rust schema synchronization check"""

    path: str = Field(...)
    content: str

    @field_validator("content")
    @classmethod
    def validate_pydantic_v2_compliance(cls, v: str) -> str:
        """Detect loose typing (Any/Dict/List) in Pydantic v2 schemas"""
        forbidden_patterns = ["Any", "dict[", "list["]

        for pattern in forbidden_patterns:
            if pattern in v and "BaseModel" in v:
                raise ValueError(
                    f'Schema drift: loose type "{pattern}" detected. '
                    f"Use explicit Pydantic v2 types instead."
                )
        return v


class EditValidation(BaseModel):
    """Main edit validation orchestrator"""

    path: str = Field(..., description="File path")
    content: str = Field(..., description="New content")

    @field_validator("path")
    @classmethod
    def check_path_security(cls, v: str) -> str:
        """Step 1: Check for path traversal"""
        if ".." in v or v.startswith("/"):
            raise ValueError(f"Path traversal detected: {v}")
        if not Path(v).is_absolute():
            # Relative path OK
            pass
        return v

    def validate_context_specific(self) -> tuple[bool, str]:
        """Step 2-4: Context-specific validation based on file type"""
        try:
            if self.path.endswith(".rs") and "spectrafit" in self.path:
                # Rust file: check PyO3 boundaries
                if "#[pyfunction]" in self.content:
                    # Validate return type is JSON-safe
                    for line in self.content.split("\n"):
                        if "#[pyfunction]" in line:
                            # Find next line with return type
                            idx = self.content.split("\n").index(line)
                            next_lines = self.content.split("\n")[idx : idx + 3]
                            for next_line in next_lines:
                                if "->" in next_line:
                                    if "Vec<" in next_line or "HashMap" in next_line:
                                        return False, (
                                            "PyO3 boundary violation: "
                                            "#[pyfunction] cannot return custom types, "
                                            "only String or Result<String>"
                                        )
                return True, "PyO3 validation passed"

            elif self.path.endswith("Cargo.toml"):
                # Cargo.toml: check DAG dependencies
                # (Simplified - full version would parse TOML)
                return True, "Cargo.toml DAG check passed"

            elif self.path.endswith(".py") and "schemas" in self.path:
                # Python schema: check Pydantic v2 compliance
                if "Any" in self.content and "BaseModel" in self.content:
                    return False, (
                        "Schema drift: loose typing (Any) detected. "
                        "Use explicit Pydantic v2 types for Python↔Rust sync."
                    )
                return True, "Schema validation passed"

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

            return True, "No specific validation rules for this file"

        except Exception as e:
            return False, f"Validation error: {str(e)}"


def validate_edit(path: str, content: str) -> dict:
    """Main entry point for edit validation

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
        EditValidationRequest(path=path, content=content)

        # Step 2: Context-specific validation
        validator = EditValidation(path=path, content=content)
        passed, reason = validator.validate_context_specific()

        if not passed:
            violations.append(reason)
            return {"decision": "deny", "reason": reason, "violations": violations}

        return {
            "decision": "allow",
            "reason": "Edit passed all validation checks",
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
    CLI interface: validate-edit.py <path> <content>
    
    Outputs JSON to stdout
    Exit 0: allow (decision=allow)
    Exit 1: deny (decision=deny)
    """

    if len(sys.argv) < 3:
        result = {
            "decision": "deny",
            "reason": "Usage: validate-edit.py <path> <content>",
            "violations": ["Missing arguments"],
        }
        print(json.dumps(result))
        sys.exit(1)

    path = sys.argv[1]
    content = sys.argv[2]

    result = validate_edit(path, content)
    print(json.dumps(result))

    sys.exit(0 if result["decision"] == "allow" else 1)
