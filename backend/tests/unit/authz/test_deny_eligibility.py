"""Unit tests for the deny-eligible resource type allowlist (AAP-74620 / ANSTRAT-1750).

Tests cover:
- Only ``workflow_node`` may be targeted by a deny-effect statement
- Allow-effect statements are never inspected
- Wildcard and multi-action statements are handled per action string
- The recovery resources (policy, role, role-assignment, user) can never be denied
"""

import pytest

from syntara.authz.deny_eligibility import (
    DENY_ELIGIBLE_RESOURCE_TYPES,
    deny_not_allowed_message,
    find_ineligible_deny_actions,
)


class TestAllowlist:
    """The allowlist itself is the lockout guard."""

    def test_only_workflow_node_is_eligible(self) -> None:
        assert frozenset({"workflow_node"}) == DENY_ELIGIBLE_RESOURCE_TYPES

    @pytest.mark.parametrize("recovery_type", ["policy", "role", "role-assignment", "user", "group"])
    def test_recovery_resources_are_never_eligible(self, recovery_type: str) -> None:
        assert recovery_type not in DENY_ELIGIBLE_RESOURCE_TYPES


class TestFindIneligibleDenyActions:
    """Verify per-action inspection of deny-effect statements."""

    def test_deny_on_workflow_node_is_eligible(self) -> None:
        stmts = [{"effect": "deny", "actions": ["workflow_node:execute"]}]
        assert find_ineligible_deny_actions(stmts) == []

    def test_deny_wildcard_on_workflow_node_is_eligible(self) -> None:
        stmts = [{"effect": "deny", "actions": ["workflow_node:*"]}]
        assert find_ineligible_deny_actions(stmts) == []

    def test_deny_on_workflow_is_ineligible(self) -> None:
        stmts = [{"effect": "deny", "actions": ["workflow:read"]}]
        assert find_ineligible_deny_actions(stmts) == ["workflow:read"]

    def test_deny_on_policy_delete_is_ineligible(self) -> None:
        stmts = [{"effect": "deny", "actions": ["policy:delete", "role-assignment:revoke"]}]
        assert find_ineligible_deny_actions(stmts) == ["policy:delete", "role-assignment:revoke"]

    def test_mixed_actions_report_only_ineligible(self) -> None:
        stmts = [{"effect": "deny", "actions": ["workflow_node:write", "workflow:update"]}]
        assert find_ineligible_deny_actions(stmts) == ["workflow:update"]

    def test_allow_statements_are_ignored(self) -> None:
        stmts = [{"effect": "allow", "actions": ["policy:delete"]}]
        assert find_ineligible_deny_actions(stmts) == []

    def test_multiple_statements_inspected_independently(self) -> None:
        stmts = [
            {"effect": "allow", "actions": ["workflow:read"]},
            {"effect": "deny", "actions": ["workflow_node:execute"]},
            {"effect": "deny", "actions": ["credential:use"]},
        ]
        assert find_ineligible_deny_actions(stmts) == ["credential:use"]

    def test_statement_without_actions(self) -> None:
        assert find_ineligible_deny_actions([{"effect": "deny"}]) == []

    def test_empty_statements(self) -> None:
        assert find_ineligible_deny_actions([]) == []


class TestMessage:
    """The error names both the allowlist and the offending actions."""

    def test_message_lists_eligible_and_offending(self) -> None:
        msg = deny_not_allowed_message(["workflow:read", "policy:delete"])
        assert "workflow_node" in msg
        assert "workflow:read, policy:delete" in msg
