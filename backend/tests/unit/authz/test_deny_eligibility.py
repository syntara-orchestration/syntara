"""Deny policy validation keeps recovery actions available (AAP-74620)."""

from typing import Any

import pytest

from syntara.authz.deny_eligibility import (
    DENY_ELIGIBLE_RESOURCE_TYPES,
    find_ineligible_deny_actions,
    validate_deny_statements,
)


def test_only_step_type_is_deny_eligible() -> None:
    assert {"step_type"} == DENY_ELIGIBLE_RESOURCE_TYPES


@pytest.mark.parametrize("scope", ["any", "project"])
def test_write_is_eligible(scope: str) -> None:
    assert validate_deny_statements([{"effect": "deny", "actions": ["step_type:write"], "scope": scope}]) is None


@pytest.mark.parametrize(
    "action",
    [
        "step_type:*",
        "step_type:execute",
        "workflow_node:write",
        "policy:delete",
        "role:delete",
        "role-assignment:revoke",
        "user:*",
        "*",
        "malformed",
    ],
)
def test_ineligible_actions_are_named(action: str) -> None:
    statements = [{"effect": "deny", "actions": ["step_type:write", action], "scope": "any"}]
    assert find_ineligible_deny_actions(statements) == [action]
    assert action in (validate_deny_statements(statements) or "")


@pytest.mark.parametrize("scope", ["self", "own", "system", None])
def test_ineligible_scope_is_rejected(scope: str | None) -> None:
    error = validate_deny_statements([{"effect": "deny", "actions": ["step_type:write"], "scope": scope}])
    assert error is not None
    assert "scope 'any' or 'project'" in error


@pytest.mark.parametrize("statement", [{"effect": "deny"}, {"effect": "deny", "actions": []}])
def test_empty_deny_actions_are_rejected(statement: dict[str, Any]) -> None:
    assert "require the action" in (validate_deny_statements([statement]) or "")


def test_allow_statements_and_empty_input_are_unchanged() -> None:
    assert validate_deny_statements([]) is None
    assert validate_deny_statements([{"effect": "allow", "actions": ["policy:delete"], "scope": "self"}]) is None
    assert validate_deny_statements([{"effect": "allow", "actions": None}]) is None


@pytest.mark.parametrize(
    "actions",
    [
        None,
        123,
        False,
        1.5,
        "step_type:write",
        b"step_type:write",
        {"step_type:write": True},
        ("step_type:write",),
        {"step_type:write"},
    ],
)
def test_non_list_actions_are_rejected(actions: object) -> None:
    statements = [{"effect": "deny", "actions": actions, "scope": "any"}]
    assert validate_deny_statements(statements) == "Deny-effect actions must be a list"


def test_later_deny_action_container_is_validated_before_iteration() -> None:
    statements: list[dict[str, Any]] = [
        {"effect": "allow", "actions": ["policy:delete"]},
        {"effect": "deny", "actions": ["step_type:write"], "scope": "any"},
        {"effect": "deny", "actions": None, "scope": "project"},
    ]
    assert validate_deny_statements(statements) == "Deny-effect actions must be a list"


@pytest.mark.parametrize(
    ("actions", "bad"),
    [
        ([None], "None"),
        ([123], "123"),
        (["step_type:write", None], "None"),
        (["workflow_node:write", 42], "42"),
    ],
)
def test_non_string_actions_are_rejected(actions: list[Any], bad: str) -> None:
    statements = [{"effect": "deny", "actions": actions, "scope": "any"}]
    error = validate_deny_statements(statements)
    assert error is not None
    assert "must be strings" in error
    assert bad in error


def test_every_statement_is_checked() -> None:
    statements = [
        {"effect": "allow", "actions": ["policy:delete"]},
        {"effect": "deny", "actions": ["step_type:write"], "scope": "any"},
        {"effect": "deny", "actions": ["credential:use"], "scope": "project"},
    ]
    assert find_ineligible_deny_actions(statements) == ["credential:use"]
