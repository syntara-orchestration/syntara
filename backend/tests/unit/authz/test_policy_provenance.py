"""Effective statement identity survives expansion and assignment scoping."""

from typing import Any

from syntara.authz.models.policy import Policy
from syntara.authz.models.role import Role
from syntara.authz.resolver import _add_builtin_role_statements, _expand_role_policies


def test_statement_metadata_is_server_owned() -> None:
    policy = Policy(
        name="mixed",
        statements=[
            {"effect": "allow", "actions": ["step_type:write"], "scope": "any"},
            {
                "effect": "deny",
                "actions": ["step_type:write"],
                "scope": "any",
                "name": "forged",
                "policy_name": "forged",
                "statement_index": 99,
            },
        ],
    )
    statements = policy.to_statement_dicts()
    assert [s["name"] for s in statements] == ["mixed/0", "mixed/1"]
    assert [s["policy_name"] for s in statements] == ["mixed", "mixed"]
    assert [s["statement_index"] for s in statements] == [0, 1]
    policy.statements = [policy.statements[1]]
    assert policy.to_statement_dicts()[0]["name"] == "mixed"
    assert policy.to_statement_dicts()[0]["statement_index"] == 0


def test_effective_ids_distinguish_global_and_project_assignments() -> None:
    policy = Policy(
        name="deny-scripts", statements=[{"effect": "deny", "actions": ["step_type:write"], "scope": "any"}]
    )
    role = Role(name="restricted", policy_names=[policy.name])
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for project in ("payments", "", "other", "payments"):
        _expand_role_policies(role, {policy.name: policy}, seen, result, project, None)
    assert {s["name"] for s in result} == {"deny-scripts", "deny-scripts@payments", "deny-scripts@other"}
    assert len(result) == 3
    assert all(s["policy_name"] == policy.name and s["statement_index"] == 0 for s in result)
    assert result[0]["scope"] == "project"
    assert result[0]["project"] == "payments"
    assert result[1]["scope"] == "any"
    assert policy.statements[0]["scope"] == "any"


def test_builtin_policy_identity_agrees_across_role_expansion_paths() -> None:
    direct: list[dict[str, Any]] = []
    _add_builtin_role_statements("authenticated", set(), direct, "payments")
    policy_name = direct[0]["policy_name"]
    custom: list[dict[str, Any]] = []
    _expand_role_policies(Role(name="custom", policy_names=[policy_name]), {}, set(), custom, "payments", None)
    assert custom == [direct[0]]
    assert custom[0]["name"] == f"{policy_name}@payments"
