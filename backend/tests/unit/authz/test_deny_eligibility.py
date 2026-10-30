"""Tests for deny-effect eligibility (AAP-74620 lockout guard, AAP-99937)."""

import pytest

from syntara.authz.deny_eligibility import (
    DENY_ELIGIBLE_RESOURCE_TYPES,
    deny_eligible_actions,
    deny_not_allowed_message,
    find_ineligible_deny_actions,
)
from syntara.workflows.node_kinds import NODE_ACTION_WRITE, NODE_RESOURCE_TYPE


def test_deny_eligible_resource_types_track_step_type() -> None:
    """Drift guard: the allowlist must name the registered step-type resource."""
    assert {NODE_RESOURCE_TYPE} == DENY_ELIGIBLE_RESOURCE_TYPES


def test_only_step_type_write_is_deny_eligible() -> None:
    """No other resource type — and no other step_type action — may carry deny."""
    assert deny_eligible_actions(NODE_RESOURCE_TYPE) == {NODE_ACTION_WRITE}
    assert deny_eligible_actions("workflow") == frozenset()
    assert deny_eligible_actions("policy") == frozenset()
    assert deny_eligible_actions("role-assignment") == frozenset()


@pytest.mark.parametrize(
    ("statements", "expected"),
    [
        ([{"effect": "deny", "actions": ["step_type:write"]}], []),
        ([{"effect": "allow", "actions": ["workflow:read"]}], []),
        ([{"effect": "deny", "actions": ["workflow:read"]}], ["workflow:read"]),
        ([{"effect": "deny", "actions": ["policy:delete"]}], ["policy:delete"]),
        ([{"effect": "deny", "actions": ["role-assignment:revoke"]}], ["role-assignment:revoke"]),
        ([{"effect": "deny", "actions": ["step_type:*"]}], ["step_type:*"]),
        ([{"effect": "deny", "actions": ["step_type:read"]}], ["step_type:read"]),
        ([{"effect": "deny", "actions": ["step_type:write", "workflow:read"]}], ["workflow:read"]),
        ([{"effect": "deny", "actions": []}], ["<no actions>"]),
        ([], []),
    ],
)
def test_find_ineligible_deny_actions(statements: list[dict[str, object]], expected: list[str]) -> None:
    """Only deny statements on step_type:write pass; everything else is named."""
    assert find_ineligible_deny_actions(statements) == expected


def test_deny_not_allowed_message_names_the_offending_actions() -> None:
    """The error message states the eligible pair and the rejected actions."""
    message = deny_not_allowed_message(["workflow:read", "policy:delete"])
    assert "step_type:write" in message
    assert "workflow:read" in message
    assert "policy:delete" in message
