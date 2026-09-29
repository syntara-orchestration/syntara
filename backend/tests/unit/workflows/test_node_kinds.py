"""Step-kind policy registry and statement validation."""

from typing import Any

import pytest

from syntara.authz.role_conventions import BUILTIN_POLICIES, builtin_policy_uuid
from syntara.workflows.node_kinds import (
    NODE_KINDS,
    REGISTERED_STEP_KINDS,
    node_kind_action_pairs,
    validate_node_kind_statements,
)
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType


def _statement(action: str, kind: str, **labels: str) -> dict[str, Any]:
    return {
        "effect": "deny",
        "actions": [f"workflow_node:{action}"],
        "scope": "any",
        "conditions": {"resource_labels": {"kind": kind, **labels}},
    }


def test_registry_tracks_node_types_and_only_exposes_execute() -> None:
    assert tuple(kind.value for kind in NodeType) == NODE_KINDS
    assert node_kind_action_pairs() == frozenset({("workflow_node", "execute")})


def test_builtins_are_unassigned_denies_for_every_registered_kind_except_mcp_tool() -> None:
    policies = {policy.name: policy for policy in BUILTIN_POLICIES}
    expected_kinds = set(REGISTERED_STEP_KINDS) - {"mcp_tool"}
    actual = {
        (policy.scope, policy.kind)
        for policy in BUILTIN_POLICIES
        if policy.name.startswith("workflow_node:execute:") and policy.effect == "deny"
    }
    expected = {(scope, kind) for scope in ("any", "project") for kind in expected_kinds}
    assert actual == expected

    for scope, kind in expected:
        name = f"workflow_node:execute:{scope}:{kind}"
        policy = policies[name]
        assert policy.roles == ()
        assert policy.scope == scope
        assert policy.statements == [
            {
                "effect": "deny",
                "actions": ["workflow_node:execute"],
                "scope": scope,
                "conditions": {"resource_labels": {"kind": kind}},
            }
        ]
    assert str(builtin_policy_uuid("workflow_node:execute:any:script")) == "fceb7564-e160-50d0-b83b-a9b0e61023f8"


@pytest.mark.parametrize("kind", REGISTERED_STEP_KINDS)
def test_registered_step_policy_statement_is_valid(kind: str) -> None:
    assert validate_node_kind_statements([_statement("execute", kind)]) is None


def test_unknown_kind_is_rejected() -> None:
    error = validate_node_kind_statements([_statement("execute", "http_requst")])
    assert error is not None
    assert "Unknown node kind 'http_requst'" in error


def test_extra_resource_labels_are_rejected() -> None:
    error = validate_node_kind_statements([_statement("execute", "script", language="python")])
    assert error == "workflow_node policies require only conditions.resource_labels.kind"


def test_workflow_node_write_and_wildcard_actions_are_rejected() -> None:
    assert (
        validate_node_kind_statements([_statement("write", "script")])
        == "workflow_node supports only the execute action"
    )
    assert (
        validate_node_kind_statements([_statement("*", "script")]) == "workflow_node supports only the execute action"
    )


def test_kind_is_required_for_workflow_node_policy() -> None:
    statement = {"effect": "deny", "actions": ["workflow_node:execute"], "scope": "any"}
    assert (
        validate_node_kind_statements([statement])
        == "workflow_node policies require only conditions.resource_labels.kind"
    )
