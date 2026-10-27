"""The policy kind contract covers every backend step type."""

import json
from pathlib import Path
from typing import Any

import pytest

from syntara.workflows.node_kinds import NODE_KINDS, node_labels, validate_node_kind_statements
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType


def test_registry_and_schema_catalog_match_node_types() -> None:
    """Frontend mapping tests consume this catalog, so it must match the enum."""
    catalog_path = (
        Path(__file__).resolve().parents[3] / "src/syntara/schemas/workflows/v2/catalog/node_type_catalog.json"
    )
    catalog = json.loads(catalog_path.read_text())
    assert {node_type.value for node_type in NodeType} == NODE_KINDS
    assert {entry["type"] for entry in catalog["node_types"]} == NODE_KINDS


@pytest.mark.parametrize("node_type", list(NodeType))
@pytest.mark.parametrize("condition", ["resource_labels", "resource_labels_not"])
def test_every_node_type_is_a_valid_kind(node_type: NodeType, condition: str) -> None:
    """Triggers and flow-control types use the same contract as actions."""
    statements = [{"actions": ["step_type:write"], "conditions": {condition: {"kind": node_type.value}}}]
    assert validate_node_kind_statements(statements) is None


@pytest.mark.parametrize("action", ["step_type:write", "step_type:*"])
@pytest.mark.parametrize("labels", [{"kind": "scritp"}, {"kind": "*"}, {"kind": []}, {"kind": None}])
def test_unknown_or_malformed_kind_rejected(action: str, labels: dict[str, Any]) -> None:
    """Unknown values cannot silently create policies that match nothing."""
    error = validate_node_kind_statements([{"actions": [action], "conditions": {"resource_labels": labels}}])
    assert error is not None
    assert "Unknown step type" in error
    assert str(labels["kind"]) in error


@pytest.mark.parametrize("conditions", [None, {}, {"resource_labels": {}}, {"resource_labels_not": {}}])
def test_kind_condition_is_optional(conditions: dict[str, Any] | None) -> None:
    """A statement without kind targets every step type."""
    assert validate_node_kind_statements([{"actions": ["step_type:write"], "conditions": conditions}]) is None


def test_other_resource_conditions_unchanged() -> None:
    """Other resources continue to accept arbitrary labels."""
    assert (
        validate_node_kind_statements(
            [{"actions": ["workflow:read"], "conditions": {"resource_labels": {"kind": "custom", "team": "ops"}}}]
        )
        is None
    )


@pytest.mark.parametrize("node", [{}, {"type": None}, {"type": ""}, {"type": []}])
def test_node_labels_without_a_type(node: dict[str, Any]) -> None:
    """Incomplete steps have no policy labels."""
    assert node_labels(node) == {}


def test_node_labels_excludes_parameters() -> None:
    """Parameters are neither policy selectors nor exposed resource labels."""
    assert node_labels({"type": "script", "parameters": {"language": "bash", "code": "secret"}}) == {"kind": "script"}
