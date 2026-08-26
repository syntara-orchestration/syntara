"""Tests for workflow definition size and complexity bounds (AAP-87165).

Verifies that the validator rejects oversized definitions and high
node-count chains with error-severity findings.
"""

import json
from typing import Any

import pytest

from syntara.core.constants import WorkflowDefinitionLimits
from syntara.core.exceptions import SafeValueError
from syntara.workflows.models.validation_finding import (
    ValidationCategory,
    ValidationSeverity,
)
from syntara.workflows.validators.workflow_definition import WorkflowValidator


@pytest.fixture
def validator() -> WorkflowValidator:
    return WorkflowValidator()


def _valid_definition() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "test-workflow",
        "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
        "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "print(1)"}}],
        "edges": [{"from": "t1", "to": "n1"}],
    }


def _oversized_definition(target_bytes: int) -> dict[str, Any]:
    """Build a definition whose serialized size exceeds *target_bytes*."""
    defn = _valid_definition()
    defn["nodes"][0]["parameters"]["code"] = ""
    shell_size = len(json.dumps(defn).encode())
    defn["nodes"][0]["parameters"]["code"] = "x" * (target_bytes - shell_size + 1)
    assert len(json.dumps(defn).encode()) > target_bytes
    return defn


def _many_nodes_definition(node_count: int) -> dict[str, Any]:
    """Build a definition with *node_count* script nodes in a linear chain."""
    trigger_id = "t1"
    nodes = [
        {
            "id": f"node_{i}",
            "type": "script",
            "parameters": {"language": "python", "code": "pass"},
        }
        for i in range(node_count)
    ]
    edges: list[dict[str, str]] = [{"from": trigger_id, "to": "node_0"}]
    for i in range(node_count - 1):
        edges.append({"from": f"node_{i}", "to": f"node_{i + 1}"})

    return {
        "schema_version": "2.0.0",
        "name": f"chain-{node_count}",
        "triggers": [{"id": trigger_id, "type": "manual_trigger", "parameters": {}}],
        "nodes": nodes,
        "edges": edges,
    }


class TestDefinitionSizeLimits:
    """Oversized definitions are rejected."""

    def test_oversized_definition_raises(self, validator: WorkflowValidator) -> None:
        defn = _oversized_definition(target_bytes=WorkflowDefinitionLimits.MAX_DEFINITION_BYTES)
        with pytest.raises(SafeValueError, match="too large"):
            validator.validate_workflow_definition(defn)

    def test_oversized_definition_error_findings(self, validator: WorkflowValidator) -> None:
        defn = _oversized_definition(target_bytes=WorkflowDefinitionLimits.MAX_DEFINITION_BYTES)
        result = validator.collect_findings(defn)
        errors = [f for f in result.findings if f.severity == ValidationSeverity.error]
        assert len(errors) == 1
        assert errors[0].category == ValidationCategory.definition_limits
        assert "too large" in errors[0].message

    def test_just_under_limit_accepted(self, validator: WorkflowValidator) -> None:
        defn = _valid_definition()
        defn["nodes"][0]["parameters"]["code"] = ""
        shell_size = len(json.dumps(defn).encode())
        remaining = WorkflowDefinitionLimits.MAX_DEFINITION_BYTES - shell_size
        defn["nodes"][0]["parameters"]["code"] = "x" * remaining
        assert len(json.dumps(defn).encode()) <= WorkflowDefinitionLimits.MAX_DEFINITION_BYTES
        validator.validate_workflow_definition(defn)


class TestNodeCountLimits:
    """High node-count definitions are rejected."""

    def test_too_many_nodes_raises(self, validator: WorkflowValidator) -> None:
        defn = _many_nodes_definition(node_count=WorkflowDefinitionLimits.MAX_NODES + 1)
        with pytest.raises(SafeValueError, match="too many nodes"):
            validator.validate_workflow_definition(defn)

    def test_too_many_nodes_error_findings(self, validator: WorkflowValidator) -> None:
        defn = _many_nodes_definition(node_count=WorkflowDefinitionLimits.MAX_NODES + 1)
        result = validator.collect_findings(defn)
        errors = [f for f in result.findings if f.severity == ValidationSeverity.error]
        assert any(f.category == ValidationCategory.definition_limits for f in errors)
        assert any("too many nodes" in f.message for f in errors)

    def test_at_limit_accepted(self, validator: WorkflowValidator) -> None:
        defn = _many_nodes_definition(node_count=WorkflowDefinitionLimits.MAX_NODES)
        result = validator.collect_findings(defn)
        limit_errors = [
            f
            for f in result.findings
            if f.severity == ValidationSeverity.error and f.category == ValidationCategory.definition_limits
        ]
        assert len(limit_errors) == 0
