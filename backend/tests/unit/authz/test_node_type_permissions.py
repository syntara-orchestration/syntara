"""Unit tests for workflow node-type permission inheritance and redaction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from syntara.authz.node_type_permissions import (
    PERMISSION_REDACTED_KEY,
    NodeTypeAccess,
    _node_permission_errors,
    _removal_permission_errors,
    _restore_read_denied_items,
    _trigger_permission_errors,
    iter_definition_node_types,
    validate_workflow_definition_node_permissions,
)
from syntara.authz.workflow_node_type_catalog import load_node_type_catalog_entries
from syntara.authz.workflow_node_type_policies import WORKFLOW_NODE_TYPE_POLICIES

if TYPE_CHECKING:
    import pytest

FULL_ACCESS = NodeTypeAccess(read=True, write=True, execute=True)
READ_ONLY = NodeTypeAccess(read=True, write=False, execute=True)
READ_DENIED = NodeTypeAccess(read=False, write=True, execute=True)
NO_ACCESS = NodeTypeAccess(read=False, write=False, execute=False)


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


def test_removal_without_write_errors() -> None:
    previous = {"n1": {"id": "n1", "type": "script", "parameters": {"code": "x"}}}
    errors = _removal_permission_errors(previous, set(), {"script": NO_ACCESS}, kind="Node")
    assert errors == ["Node 'n1' (script) cannot be removed with your permissions"]


def test_removal_with_read_denied_is_rejected_even_if_write_allowed() -> None:
    previous = {"n1": {"id": "n1", "type": "script", "parameters": {"code": "x"}}}
    errors = _removal_permission_errors(previous, set(), {"script": READ_DENIED}, kind="Node")
    assert errors == ["Node 'n1' (script) cannot be removed with your permissions"]


async def test_validator_rejects_removing_read_denied_node(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "syntara.authz.node_type_permissions.resolve_node_type_permissions",
        AsyncMock(return_value={"script": READ_DENIED}),
    )
    previous_node = {"id": "n1", "type": "script", "parameters": {"code": "secret"}}

    errors = await validate_workflow_definition_node_permissions(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        project_id=uuid4(),
        workflow_definition={"nodes": [], "triggers": []},
        previous_definition={"nodes": [previous_node], "triggers": []},
    )

    assert errors == ["Node 'n1' (script) cannot be removed with your permissions"]


def test_keep_read_denied_existing_node_restores_previous_body() -> None:
    previous_node = {"id": "n1", "type": "script", "parameters": {"code": "secret"}}
    submitted = [{"id": "n1", "type": "script", PERMISSION_REDACTED_KEY: True}]
    restored, errors = _node_permission_errors(
        submitted,
        {"script": READ_DENIED},
        {"n1": previous_node},
        {"nodes": [previous_node]},
    )
    assert errors == []
    assert restored == [previous_node]
    assert restored[0]["parameters"] == {"code": "secret"}


def test_add_new_read_denied_node_errors() -> None:
    submitted = [{"id": "n1", "type": "script", "parameters": {"code": "x"}}]
    _restored, errors = _node_permission_errors(submitted, {"script": READ_DENIED}, {}, None)
    assert errors == ["Node 'n1' uses type 'script' which you are not allowed to read"]


def test_add_new_write_denied_node_errors() -> None:
    submitted = [{"id": "n1", "type": "script", "parameters": {"code": "x"}}]
    _restored, errors = _node_permission_errors(submitted, {"script": READ_ONLY}, {}, None)
    assert errors == ["Node 'n1' (script) cannot be added with your permissions"]


def test_unchanged_write_denied_node_allowed() -> None:
    node = {"id": "n1", "type": "script", "parameters": {"code": "x"}}
    restored, errors = _node_permission_errors(
        [node],
        {"script": READ_ONLY},
        {"n1": node},
        {"nodes": [node]},
    )
    assert errors == []
    assert restored == [node]


def test_modified_write_denied_node_errors() -> None:
    previous = {"id": "n1", "type": "script", "parameters": {"code": "old"}}
    submitted = {"id": "n1", "type": "script", "parameters": {"code": "new"}}
    _restored, errors = _node_permission_errors(
        [submitted],
        {"script": READ_ONLY},
        {"n1": previous},
        {"nodes": [previous]},
    )
    assert errors == ["Node 'n1' (script) is read-only for your account"]


def test_trigger_removal_without_write_errors() -> None:
    previous = {"t1": {"id": "t1", "type": "manual_trigger"}}
    errors = _removal_permission_errors(previous, set(), {"manual_trigger": NO_ACCESS}, kind="Trigger")
    assert errors == ["Trigger 't1' (manual_trigger) cannot be removed with your permissions"]


def test_keep_read_denied_existing_trigger_restores_previous() -> None:
    previous_trigger: dict[str, Any] = {
        "id": "t1",
        "type": "webhook_trigger",
        "parameters": {"path": "/secret"},
    }
    submitted = [{"id": "t1", "type": "webhook_trigger", PERMISSION_REDACTED_KEY: True}]
    restored, errors = _trigger_permission_errors(
        submitted,
        {"webhook_trigger": READ_DENIED},
        {"t1": previous_trigger},
        {"triggers": [previous_trigger]},
    )
    assert errors == []
    assert restored == [previous_trigger]


def test_restore_helper_matches_node_and_trigger_paths() -> None:
    previous = {"id": "x1", "type": "script", "parameters": {"a": 1}}
    restored, errors = _restore_read_denied_items(
        [{"id": "x1", "type": "script", PERMISSION_REDACTED_KEY: True}],
        {"x1": previous},
        {"script": READ_DENIED},
        kind="Node",
        previous_definition={"nodes": [previous]},
    )
    assert errors == []
    assert restored[0] is not previous
    assert restored[0] == previous
