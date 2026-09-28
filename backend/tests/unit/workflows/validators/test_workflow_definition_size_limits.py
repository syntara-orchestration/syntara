"""Tests for workflow definition node/edge count limits (AAP-87165).

Size (byte) limits are enforced at the API layer by WorkflowDefinitionValidator
on model fields and tested in tests/unit/core/utils/test_jsonb_limits.py.
These tests cover the validator-layer structural complexity checks that return
structured ValidationFinding objects for UI feedback.
"""

from typing import Any

import pytest

from syntara.core.constants import JsonbLimits
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


def _many_edges_definition(edge_count: int) -> dict[str, Any]:
    """Build a definition with *edge_count* total edges.

    The limit check runs before graph validation, so edges don't need
    to reference real nodes — we just need the right count.
    """
    trigger_id = "t1"
    return {
        "schema_version": "2.0.0",
        "name": f"edges-{edge_count}",
        "triggers": [{"id": trigger_id, "type": "manual_trigger", "parameters": {}}],
        "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
        "edges": [{"from": trigger_id, "to": "n1"}] * edge_count,
    }


class TestNodeCountLimits:
    """High node-count definitions are rejected."""

    def test_too_many_nodes_raises(self, validator: WorkflowValidator) -> None:
        defn = _many_nodes_definition(node_count=JsonbLimits.MAX_WORKFLOW_NODES + 1)
        with pytest.raises(SafeValueError, match="too many nodes"):
            validator.validate_workflow_definition(defn)

    def test_too_many_nodes_error_findings(self, validator: WorkflowValidator) -> None:
        defn = _many_nodes_definition(node_count=JsonbLimits.MAX_WORKFLOW_NODES + 1)
        result = validator.collect_findings(defn)
        errors = [f for f in result.findings if f.severity == ValidationSeverity.error]
        assert any(f.category == ValidationCategory.definition_limits for f in errors)
        assert any("too many nodes" in f.message for f in errors)

    def test_at_limit_accepted(self, validator: WorkflowValidator) -> None:
        defn = _many_nodes_definition(node_count=JsonbLimits.MAX_WORKFLOW_NODES)
        result = validator.collect_findings(defn)
        limit_errors = [
            f
            for f in result.findings
            if f.severity == ValidationSeverity.error and f.category == ValidationCategory.definition_limits
        ]
        assert len(limit_errors) == 0


class TestEdgeCountLimits:
    """High edge-count definitions are rejected."""

    def test_too_many_edges_raises(self, validator: WorkflowValidator) -> None:
        defn = _many_edges_definition(edge_count=JsonbLimits.MAX_WORKFLOW_EDGES + 1)
        with pytest.raises(SafeValueError, match="too many edges"):
            validator.validate_workflow_definition(defn)

    def test_too_many_edges_error_findings(self, validator: WorkflowValidator) -> None:
        defn = _many_edges_definition(edge_count=JsonbLimits.MAX_WORKFLOW_EDGES + 1)
        result = validator.collect_findings(defn)
        errors = [f for f in result.findings if f.severity == ValidationSeverity.error]
        assert any(f.category == ValidationCategory.definition_limits for f in errors)
        assert any("too many edges" in f.message for f in errors)

    def test_at_edge_limit_accepted(self, validator: WorkflowValidator) -> None:
        defn = _many_edges_definition(edge_count=JsonbLimits.MAX_WORKFLOW_EDGES)
        result = validator.collect_findings(defn)
        limit_errors = [
            f
            for f in result.findings
            if f.severity == ValidationSeverity.error and f.category == ValidationCategory.definition_limits
        ]
        assert len(limit_errors) == 0


NON_LIST_VALUES = [None, "oops", 5, {"a": 1}]


class TestNonListGuards:
    """Non-list nodes/edges must not raise TypeError (regression for isinstance guard)."""

    @pytest.mark.parametrize("bad_value", NON_LIST_VALUES)
    def test_non_list_nodes_does_not_crash(self, validator: WorkflowValidator, bad_value: object) -> None:
        defn = _valid_definition()
        defn["nodes"] = bad_value
        with pytest.raises(SafeValueError):
            validator.validate_workflow_definition(defn)

    @pytest.mark.parametrize("bad_value", NON_LIST_VALUES)
    def test_non_list_edges_does_not_crash(self, validator: WorkflowValidator, bad_value: object) -> None:
        defn = _valid_definition()
        defn["edges"] = bad_value
        with pytest.raises(SafeValueError):
            validator.validate_workflow_definition(defn)

    @pytest.mark.parametrize("bad_value", NON_LIST_VALUES)
    def test_non_list_nodes_collect_findings_does_not_crash(
        self, validator: WorkflowValidator, bad_value: object
    ) -> None:
        defn = _valid_definition()
        defn["nodes"] = bad_value
        result = validator.collect_findings(defn)
        errors = [f for f in result.findings if f.severity == ValidationSeverity.error]
        assert errors, "expected at least one error finding for malformed nodes"

    @pytest.mark.parametrize("bad_value", NON_LIST_VALUES)
    def test_non_list_edges_collect_findings_does_not_crash(
        self, validator: WorkflowValidator, bad_value: object
    ) -> None:
        defn = _valid_definition()
        defn["edges"] = bad_value
        result = validator.collect_findings(defn)
        errors = [f for f in result.findings if f.severity == ValidationSeverity.error]
        assert errors, "expected at least one error finding for malformed edges"
