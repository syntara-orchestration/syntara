"""Shared fixtures for unit-level authz tests.

Provides helpers to evaluate the authz.rego policy via regopy without any
database or API dependencies.
"""

from typing import Any

import pytest

from syntara.authz.evaluator import evaluate_policy_input


def _opa_evaluate(opa_input: dict[str, Any]) -> dict[str, Any]:
    """Evaluate authz using the real rego policy through regopy."""
    return evaluate_policy_input(opa_input)


@pytest.fixture
def opa_evaluate() -> Any:  # noqa: ANN401
    """Fixture that returns the policy evaluation function."""
    return _opa_evaluate


def build_opa_input(
    *,
    action: str,
    resource_type: str,
    resource_id: str = "",
    resource_project: str = "",
    any_project: bool = False,
    resource_labels: dict[str, str] | None = None,
    resource_metadata: dict[str, Any] | None = None,
    user_id: str = "test-user-id",
    user_labels: dict[str, str] | None = None,
    user_metadata: dict[str, Any] | None = None,
    groups: list[dict[str, Any]] | None = None,
    effective_policies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build an authz input dict matching the engine request shape."""
    return {
        "user": {
            "id": user_id,
            "labels": user_labels or {},
            "metadata": user_metadata or {},
        },
        "action": action,
        "resource": {
            "type": resource_type,
            "id": resource_id,
            "project": resource_project,
            "any_project": any_project,
            "labels": resource_labels or {},
            "metadata": resource_metadata or {},
        },
        "groups": groups or [],
        "effective_policies": effective_policies or [],
    }


def allow_policy(
    name: str,
    actions: list[str],
    scope: str = "any",
    *,
    conditions: dict[str, Any] | None = None,
    project: str = "",
) -> dict[str, Any]:
    """Build an allow policy statement dict."""
    stmt: dict[str, Any] = {
        "name": name,
        "effect": "allow",
        "actions": actions,
        "scope": scope,
    }
    if project:
        stmt["project"] = project
    if conditions is not None:
        stmt["conditions"] = conditions
    return stmt


def deny_policy(
    name: str,
    actions: list[str],
    scope: str = "any",
    *,
    conditions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deny policy statement dict."""
    stmt: dict[str, Any] = {
        "name": name,
        "effect": "deny",
        "actions": actions,
        "scope": scope,
    }
    if conditions is not None:
        stmt["conditions"] = conditions
    return stmt


def policies_for_role(role_name: str) -> list[dict[str, Any]]:
    """Resolve policy statements for a built-in role without DB access."""
    from syntara.authz.role_conventions import builtin_role_policy_names, resolve_builtin_policy_statements

    policy_names = builtin_role_policy_names(role_name)
    if not policy_names:
        msg = f"Unknown built-in role: {role_name}"
        raise ValueError(msg)

    result: list[dict[str, Any]] = []
    for policy_name in policy_names:
        for stmt in resolve_builtin_policy_statements(policy_name):
            result.append({**stmt, "name": policy_name})
    return result
