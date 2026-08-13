"""Structured validation finding models for workflow definitions.

Provides richer per-finding metadata (severity, category, field_path) and a
flat findings list with computed counts.
"""

from enum import StrEnum
from typing import ClassVar

from pydantic import ConfigDict, Field
from sqlmodel import SQLModel


class ValidationSeverity(StrEnum):
    """Severity level for a validation finding."""

    error = "error"
    warning = "warning"


class ValidationCategory(StrEnum):
    """Machine-readable classification for a validation finding."""

    schema_version = "schema_version"
    missing_field = "missing_field"
    schema_violation = "schema_violation"
    invalid_reference = "invalid_reference"
    cycle_detected = "cycle_detected"
    orphaned_node = "orphaned_node"
    converge_configuration = "converge_configuration"
    approval_configuration = "approval_configuration"


class ValidationFinding(SQLModel):
    """A single structured validation finding.

    Attributes:
        severity: error or warning
        category: Machine-readable classification
        message: Human-readable description
        node_id: Related node ID, null for workflow-level issues
        field_path: Path within node config (e.g., ``config.url``)

    """

    severity: ValidationSeverity
    category: ValidationCategory
    message: str
    node_id: str | None = None
    field_path: str | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]


class ValidationResult(SQLModel):
    """Structured validation result with flat findings list and computed counts.

    Attributes:
        is_valid: True when error_count == 0
        error_count: Count of error-severity findings
        warning_count: Count of warning-severity findings
        findings: All findings, errors first

    """

    is_valid: bool
    error_count: int
    warning_count: int
    findings: list[ValidationFinding] = Field(default_factory=list)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    @classmethod
    def from_findings(cls, findings: list[ValidationFinding]) -> "ValidationResult":
        """Build a ``ValidationResult`` from a flat list of findings."""
        errors = [f for f in findings if f.severity == ValidationSeverity.error]
        warnings = [f for f in findings if f.severity == ValidationSeverity.warning]
        sorted_findings = errors + warnings
        return cls(
            is_valid=len(errors) == 0,
            error_count=len(errors),
            warning_count=len(warnings),
            findings=sorted_findings,
        )


class DetailedValidationProblemDetail(SQLModel):
    """RFC 9457 Problem Details with a ``ValidationResult`` extension.

    Attributes:
        type: URI reference identifying the problem type
        title: Short, human-readable summary
        detail: Human-readable explanation specific to this occurrence
        code: Machine-readable error code
        instance: Optional URI reference identifying the specific occurrence
        validation_result: Structured validation findings

    """

    type: str
    title: str
    detail: str
    code: str
    instance: str | None = None
    validation_result: ValidationResult

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]
