"""Unit tests for workflow node-type permission inheritance and redaction."""

from __future__ import annotations

from syntara.authz.node_type_permissions import (
    PERMISSION_REDACTED_KEY,
    iter_definition_node_types,
)
from syntara.authz.workflow_node_type_catalog import load_node_type_catalog_entries
from syntara.authz.workflow_node_type_policies import WORKFLOW_NODE_TYPE_POLICIES


def test_catalog_loads_sixteen_node_types() -> None:
    entries = load_node_type_catalog_entries()
    assert len(entries) == 16


def test_generated_policy_count() -> None:
    assert len(WORKFLOW_NODE_TYPE_POLICIES) == 16 * 3
    assert all(p.effect == "deny" for p in WORKFLOW_NODE_TYPE_POLICIES)
    assert all(p.resource == "workflow_node_type" for p in WORKFLOW_NODE_TYPE_POLICIES)


def test_node_type_policy_names_use_deny_suffix() -> None:
    script_read = next(p for p in WORKFLOW_NODE_TYPE_POLICIES if p.name == "script:read:deny")
    assert script_read.action == "read"
    assert script_read.node_type_label is not None


def test_iter_definition_node_types_includes_nodes_and_triggers() -> None:
    definition = {
        "nodes": [{"id": "n1", "type": "script"}],
        "triggers": [{"id": "t1", "type": "manual_trigger"}],
    }
    assert iter_definition_node_types(definition) == {"script", "manual_trigger"}


def test_redact_node_shape() -> None:
    from syntara.authz.node_type_permissions import _redact_node

    node = {"id": "n1", "type": "http_request", "name": "Private", "parameters": {"url": "x"}}
    redacted = _redact_node(node, "http_request")
    assert redacted["id"] == "n1"
    assert redacted[PERMISSION_REDACTED_KEY] is True
    assert "parameters" not in redacted
