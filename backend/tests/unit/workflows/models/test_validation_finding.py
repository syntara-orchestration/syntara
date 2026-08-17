"""Tests for ValidationFinding, ValidationResult, and related models."""

import pytest

from syntara.workflows.models.validation_finding import (
    ValidationCategory,
    ValidationFinding,
    ValidationResult,
    ValidationSeverity,
)


class TestValidationFinding:
    """ValidationFinding serialization and field behavior."""

    def test_all_fields_serialized(self) -> None:
        finding = ValidationFinding(
            severity=ValidationSeverity.error,
            category=ValidationCategory.schema_violation,
            message="'parameters' is a required property",
            node_id="n1",
            field_path="parameters",
        )
        data = finding.model_dump(mode="json")
        assert data["severity"] == "error"
        assert data["category"] == "schema_violation"
        assert data["message"] == "'parameters' is a required property"
        assert data["node_id"] == "n1"
        assert data["field_path"] == "parameters"

    def test_nullable_fields_default_to_none(self) -> None:
        finding = ValidationFinding(
            severity=ValidationSeverity.warning,
            category=ValidationCategory.orphaned_node,
            message="Node has no edges",
        )
        assert finding.node_id is None
        assert finding.field_path is None

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            ValidationFinding(
                severity=ValidationSeverity.error,
                category=ValidationCategory.schema_violation,
                message="test",
                extra_field="bad",
            )


class TestValidationResult:
    """ValidationResult construction and computed properties."""

    def test_from_findings_errors_first(self) -> None:
        findings = [
            ValidationFinding(
                severity=ValidationSeverity.warning,
                category=ValidationCategory.orphaned_node,
                message="orphaned",
                node_id="n2",
            ),
            ValidationFinding(
                severity=ValidationSeverity.error,
                category=ValidationCategory.schema_violation,
                message="bad schema",
                node_id="n1",
            ),
        ]
        result = ValidationResult.from_findings(findings)
        assert result.is_valid is False
        assert result.error_count == 1
        assert result.warning_count == 1
        assert result.findings[0].severity == ValidationSeverity.error
        assert result.findings[1].severity == ValidationSeverity.warning

    def test_from_findings_empty(self) -> None:
        result = ValidationResult.from_findings([])
        assert result.is_valid is True
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.findings == []

    def test_from_findings_warnings_only_is_valid(self) -> None:
        findings = [
            ValidationFinding(
                severity=ValidationSeverity.warning,
                category=ValidationCategory.orphaned_node,
                message="orphaned node",
                node_id="n1",
            ),
        ]
        result = ValidationResult.from_findings(findings)
        assert result.is_valid is True
        assert result.error_count == 0
        assert result.warning_count == 1


class TestJsonSerialization:
    """End-to-end JSON serialization matches expected API shape."""

    def test_validation_result_json_shape(self) -> None:
        findings = [
            ValidationFinding(
                severity=ValidationSeverity.error,
                category=ValidationCategory.invalid_reference,
                message="Edge references non-existent node 'ghost'",
                node_id="ghost",
            ),
        ]
        result = ValidationResult.from_findings(findings)
        data = result.model_dump(mode="json")
        assert data == {
            "is_valid": False,
            "error_count": 1,
            "warning_count": 0,
            "findings": [
                {
                    "severity": "error",
                    "category": "invalid_reference",
                    "message": "Edge references non-existent node 'ghost'",
                    "node_id": "ghost",
                    "field_path": None,
                },
            ],
        }
