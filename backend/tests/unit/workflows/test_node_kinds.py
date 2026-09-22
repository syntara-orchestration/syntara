"""Unit tests for the declarative node-kind registry (ANSTRAT-1750).

Tests cover:
- Every ``NodeType`` value is registered exactly once with a category
- Deniable actions follow the category (trigger: write; flow control: none; action: both)
- The resource-action pairs contributed to the authz registry
- ``kind`` label validation on ``workflow_node`` policy statements
"""

from typing import Any

import pytest

from syntara.workflows.node_kinds import (
    NODE_ACTIONS,
    NODE_KIND_LABEL,
    NODE_KINDS,
    NODE_RESOURCE_TYPE,
    NodeKindCategory,
    all_node_kinds,
    deniable_node_kinds,
    get_node_kind,
    node_kind_action_pairs,
    node_kinds_by_category,
    validate_node_kind_statements,
)
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType


def _stmt(
    effect: str,
    actions: list[str],
    kind: str | None = None,
    *,
    conditions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stmt: dict[str, Any] = {"effect": effect, "actions": actions, "scope": "any"}
    if kind is not None:
        stmt["conditions"] = {"resource_labels": {NODE_KIND_LABEL: kind}}
    elif conditions is not None:
        stmt["conditions"] = conditions
    return stmt


class TestRegistryCoverage:
    """The registry mirrors the NodeType enum exactly."""

    def test_every_node_type_registered_once(self) -> None:
        kinds = [info.kind for info in NODE_KINDS]
        assert sorted(kinds) == sorted(nt.value for nt in NodeType)
        assert len(kinds) == len(set(kinds))

    def test_all_node_kinds_returns_registry(self) -> None:
        assert all_node_kinds() == NODE_KINDS

    def test_get_node_kind_known(self) -> None:
        info = get_node_kind("http_request")
        assert info is not None
        assert info.category is NodeKindCategory.ACTION

    def test_get_node_kind_unknown(self) -> None:
        assert get_node_kind("http_requst") is None

    def test_categories_partition_registry(self) -> None:
        by_category = {c: node_kinds_by_category(c) for c in NodeKindCategory}
        total = sum(len(v) for v in by_category.values())
        assert total == len(NODE_KINDS)
        assert {i.kind for i in by_category[NodeKindCategory.TRIGGER]} == {
            "manual_trigger",
            "scheduled_trigger",
            "webhook_trigger",
            "eda_trigger",
        }
        assert {i.kind for i in by_category[NodeKindCategory.FLOW_CONTROL]} == {
            "condition",
            "converge",
            "loop",
            "switch",
            "wait",
            "permission_check",
        }


class TestDeniableActions:
    """Which actions a deny may target depends on the category."""

    def test_action_kind_deniable_for_both(self) -> None:
        info = get_node_kind("script")
        assert info is not None
        assert info.deniable_actions == NODE_ACTIONS
        assert info.is_deniable("*")

    def test_trigger_kind_deniable_for_write_only(self) -> None:
        info = get_node_kind("webhook_trigger")
        assert info is not None
        assert info.is_deniable("write")
        assert not info.is_deniable("execute")
        assert info.is_deniable("*")

    def test_flow_control_kind_never_deniable(self) -> None:
        info = get_node_kind("condition")
        assert info is not None
        assert info.deniable_actions == frozenset()
        assert not info.is_deniable("write")
        assert not info.is_deniable("*")

    def test_deniable_node_kinds_execute_excludes_triggers_and_flow_control(self) -> None:
        kinds = deniable_node_kinds("execute")
        assert "http_request" in kinds
        assert "webhook_trigger" not in kinds
        assert "condition" not in kinds

    def test_deniable_node_kinds_write_includes_triggers(self) -> None:
        kinds = deniable_node_kinds("write")
        assert "webhook_trigger" in kinds
        assert "condition" not in kinds


class TestRegistryContribution:
    """Pairs contributed to the authz resource-actions registry."""

    def test_pairs(self) -> None:
        assert node_kind_action_pairs() == frozenset({(NODE_RESOURCE_TYPE, "write"), (NODE_RESOURCE_TYPE, "execute")})

    def test_resource_type_name(self) -> None:
        assert NODE_RESOURCE_TYPE == "workflow_node"


class TestValidateNodeKindStatements:
    """The kind label is checked against the registry instead of being free-form."""

    def test_statement_without_node_actions_ignored(self) -> None:
        stmts = [_stmt("deny", ["workflow:read"], kind="nonsense")]
        assert validate_node_kind_statements(stmts) is None

    def test_statement_without_kind_label_valid(self) -> None:
        stmts = [_stmt("deny", ["workflow_node:execute"])]
        assert validate_node_kind_statements(stmts) is None

    def test_other_labels_not_inspected(self) -> None:
        stmts = [_stmt("deny", ["workflow_node:execute"], conditions={"resource_labels": {"team": "x"}})]
        assert validate_node_kind_statements(stmts) is None

    def test_known_kind_valid(self) -> None:
        stmts = [_stmt("deny", ["workflow_node:execute"], kind="http_request")]
        assert validate_node_kind_statements(stmts) is None

    def test_unknown_kind_rejected(self) -> None:
        error = validate_node_kind_statements([_stmt("deny", ["workflow_node:execute"], kind="http_requst")])
        assert error is not None
        assert "Unknown node kind 'http_requst'" in error
        assert "http_request" in error

    def test_unknown_kind_rejected_on_allow_too(self) -> None:
        error = validate_node_kind_statements([_stmt("allow", ["workflow_node:write"], kind="nope")])
        assert error is not None

    def test_deny_execute_on_trigger_rejected(self) -> None:
        error = validate_node_kind_statements([_stmt("deny", ["workflow_node:execute"], kind="webhook_trigger")])
        assert error is not None
        assert "cannot be denied for node kind 'webhook_trigger'" in error

    def test_deny_write_on_trigger_valid(self) -> None:
        assert validate_node_kind_statements([_stmt("deny", ["workflow_node:write"], kind="webhook_trigger")]) is None

    def test_deny_on_flow_control_rejected(self) -> None:
        error = validate_node_kind_statements([_stmt("deny", ["workflow_node:write"], kind="condition")])
        assert error is not None
        assert "'condition' (flow_control) cannot be denied" in error

    def test_deny_wildcard_on_trigger_valid(self) -> None:
        assert validate_node_kind_statements([_stmt("deny", ["workflow_node:*"], kind="manual_trigger")]) is None

    def test_deny_wildcard_on_flow_control_rejected(self) -> None:
        assert validate_node_kind_statements([_stmt("deny", ["workflow_node:*"], kind="converge")]) is not None

    def test_allow_on_flow_control_valid(self) -> None:
        assert validate_node_kind_statements([_stmt("allow", ["workflow_node:*"], kind="converge")]) is None

    @pytest.mark.parametrize("kind", [nt.value for nt in NodeType])
    def test_every_registered_kind_accepted_on_allow(self, kind: str) -> None:
        assert validate_node_kind_statements([_stmt("allow", ["workflow_node:execute"], kind=kind)]) is None
