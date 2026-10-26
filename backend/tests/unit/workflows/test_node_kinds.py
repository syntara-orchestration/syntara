"""Unit tests for the node-kind registry (ANSTRAT-2533 P1)."""

from syntara.workflows.node_kinds import (
    NODE_ACTIONS,
    NODE_KIND_LABEL,
    NODE_KINDS,
    NODE_RESOURCE_TYPE,
    all_node_kinds,
    is_known_node_kind,
    node_kind_action_pairs,
    validate_node_kind_statements,
)
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

EXPECTED_KINDS = frozenset(
    {
        "manual_trigger",
        "scheduled_trigger",
        "webhook_trigger",
        "eda_trigger",
        "condition",
        "converge",
        "loop",
        "switch",
        "wait",
        "aap_job_template",
        "aap_workflow_job_template",
        "agentic",
        "approval",
        "http_request",
        "internal_activity",
        "script",
    }
)


class TestNodeKindRegistry:
    """The registry mirrors the NodeType enum."""

    def test_node_kinds_match_node_type_enum(self) -> None:
        assert frozenset(node_type.value for node_type in NodeType) == NODE_KINDS

    def test_registry_contains_expected_step_types(self) -> None:
        assert NODE_KINDS == EXPECTED_KINDS

    def test_all_node_kinds_returns_registry(self) -> None:
        assert all_node_kinds() == NODE_KINDS

    def test_is_known_node_kind(self) -> None:
        assert is_known_node_kind("script")
        assert is_known_node_kind("internal_activity")
        assert not is_known_node_kind("mcp_tool")
        assert not is_known_node_kind("bogus")


class TestNodeKindActionPairs:
    """The workflow_node resource contributes only the write action."""

    def test_registry_constants(self) -> None:
        assert NODE_RESOURCE_TYPE == "workflow_node"
        assert NODE_KIND_LABEL == "kind"
        assert frozenset({"write"}) == NODE_ACTIONS

    def test_node_kind_action_pairs(self) -> None:
        assert node_kind_action_pairs() == frozenset({("workflow_node", "write")})


class TestValidateNodeKindStatements:
    """Unknown kinds on workflow_node statements are rejected."""

    def test_valid_kind_passes(self) -> None:
        statements = [
            {
                "effect": "allow",
                "actions": ["workflow_node:write"],
                "scope": "any",
                "conditions": {"resource_labels": {"kind": "script"}},
            }
        ]
        assert validate_node_kind_statements(statements) is None

    def test_unknown_kind_in_resource_labels_rejected(self) -> None:
        statements = [
            {
                "effect": "allow",
                "actions": ["workflow_node:write"],
                "scope": "any",
                "conditions": {"resource_labels": {"kind": "bogus"}},
            }
        ]
        error = validate_node_kind_statements(statements)
        assert error is not None
        assert "Unknown node kind 'bogus'" in error
        assert "script" in error

    def test_unknown_kind_in_resource_labels_not_rejected(self) -> None:
        statements = [
            {
                "effect": "allow",
                "actions": ["workflow_node:write"],
                "scope": "any",
                "conditions": {"resource_labels_not": {"kind": "bogus"}},
            }
        ]
        error = validate_node_kind_statements(statements)
        assert error is not None
        assert "Unknown node kind 'bogus'" in error

    def test_non_string_kind_rejected(self) -> None:
        statements = [
            {
                "effect": "allow",
                "actions": ["workflow_node:write"],
                "scope": "any",
                "conditions": {"resource_labels": {"kind": ["script"]}},
            }
        ]
        error = validate_node_kind_statements(statements)
        assert error is not None
        assert "Unknown node kind" in error

    def test_missing_kind_label_passes(self) -> None:
        statements = [{"effect": "allow", "actions": ["workflow_node:write"], "scope": "any"}]
        assert validate_node_kind_statements(statements) is None

    def test_wildcard_action_is_kind_checked(self) -> None:
        statements = [
            {
                "effect": "allow",
                "actions": ["workflow_node:*"],
                "scope": "any",
                "conditions": {"resource_labels": {"kind": "approval"}},
            }
        ]
        assert validate_node_kind_statements(statements) is None

    def test_statements_without_workflow_node_actions_ignored(self) -> None:
        """Labels are free-form on other resource types."""
        statements = [
            {
                "effect": "allow",
                "actions": ["workflow:read"],
                "scope": "any",
                "conditions": {"resource_labels": {"kind": "bogus"}},
            }
        ]
        assert validate_node_kind_statements(statements) is None

    def test_empty_statements_pass(self) -> None:
        assert validate_node_kind_statements([]) is None
