"""A project-scoped deny on a global role assignment applies in every project (AAP-101796).

A ``scope: "project"`` statement only gets its ``project`` key when the role
that carries it is assigned to a project. Assigned globally, the statement
reaches Rego with no stamp, and a deny in that shape is evaluated like a
``scope: "any"`` deny.

The tests are split in two groups:

* the deny blocks everywhere a ``scope: "any"`` deny would;
* nothing else got wider: allows, other actions, other scopes and stamped
  denies keep their behaviour.
"""

from typing import Any

import pytest

from syntara.authz.evaluator import evaluate_policy_input
from syntara.authz.models.policy import Policy
from syntara.authz.models.role import Role
from syntara.authz.resolver import _expand_role_policies
from tests.unit.authz.conftest import allow_policy, build_opa_input, deny_policy

_WRITE = ["step_type:write"]
_SCRIPT_ONLY = {"resource_labels": {"kind": "script"}}
_BUILTIN_PROJECT_DENY = "step_type:write:project:deny:script"

# The two shapes of "no stamp": the key is absent (what the resolver emits
# for a global assignment) or present but empty.
_UNSTAMPED = pytest.mark.parametrize("stamp", [None, ""], ids=["no-project-key", "empty-project"])


def _unstamped_deny(stamp: str | None, *, conditions: dict[str, Any] | None = None) -> dict[str, Any]:
    deny = deny_policy("unstamped-deny", _WRITE, scope="project", conditions=conditions)
    if stamp is not None:
        deny["project"] = stamp
    return deny


def _evaluate(
    policies: list[dict[str, Any]],
    *,
    kind: str = "script",
    project: str = "payments",
    any_project: bool = False,
    action: str = "write",
    resource_type: str = "step_type",
) -> dict[str, Any]:
    return evaluate_policy_input(
        build_opa_input(
            action=action,
            resource_type=resource_type,
            resource_project=project,
            any_project=any_project,
            resource_labels={"kind": kind} if resource_type == "step_type" else None,
            effective_policies=policies,
        )
    )


def _expand(policy_names: list[str], custom: dict[str, Policy], project: str) -> list[dict[str, Any]]:
    """Expand a custom role the way the resolver does for one assignment."""
    role = Role(name="restricted", policy_names=policy_names)
    result: list[dict[str, Any]] = []
    _expand_role_policies(role, custom, set(), result, project, None)
    return result


# --- The deny blocks ---------------------------------------------------------


@_UNSTAMPED
@pytest.mark.parametrize("project", ["payments", "other", ""])
def test_unstamped_project_deny_blocks_in_every_project(stamp: str | None, project: str) -> None:
    result = _evaluate([allow_policy("allow-all", _WRITE), _unstamped_deny(stamp)], project=project)
    assert result["allow"] is False
    assert result["deny"] is True


@_UNSTAMPED
def test_unstamped_project_deny_is_reported_as_the_denying_policy(stamp: str | None) -> None:
    result = _evaluate([allow_policy("allow-all", _WRITE), _unstamped_deny(stamp)])
    assert result["denied_by"] == "unstamped-deny"
    assert result["denial_reason"] == "policy_deny"
    assert result["matched_policy"] == ""


@_UNSTAMPED
def test_unstamped_project_deny_blocks_the_any_project_check(stamp: str | None) -> None:
    result = _evaluate([allow_policy("allow-all", _WRITE), _unstamped_deny(stamp)], project="", any_project=True)
    assert result["allow"] is False
    assert result["deny"] is True


@_UNSTAMPED
def test_unstamped_project_deny_overrides_a_project_scoped_allow(stamp: str | None) -> None:
    allow = allow_policy("allow-payments", _WRITE, scope="project", project="payments")
    result = _evaluate([allow, _unstamped_deny(stamp)])
    assert result["allow"] is False
    assert result["denied_by"] == "unstamped-deny"


@_UNSTAMPED
def test_unstamped_project_deny_removes_every_allowed_project(stamp: str | None) -> None:
    policies = [
        allow_policy("allow-all", _WRITE),
        allow_policy("allow-payments", _WRITE, scope="project", project="payments"),
        _unstamped_deny(stamp),
    ]
    assert _evaluate(policies, project="")["allowed_projects"] == []


@_UNSTAMPED
@pytest.mark.parametrize(("kind", "allowed"), [("script", False), ("http_request", True)])
def test_unstamped_project_deny_still_honours_its_kind_selector(stamp: str | None, kind: str, *, allowed: bool) -> None:
    deny = _unstamped_deny(stamp, conditions=_SCRIPT_ONLY)
    result = _evaluate([allow_policy("allow-all", _WRITE), deny], kind=kind)
    assert result["allow"] is allowed
    assert result["deny"] is not allowed


@pytest.mark.parametrize("project", ["payments", "other"])
def test_builtin_project_deny_on_a_global_assignment_blocks(project: str) -> None:
    """Resolver output, unchanged, through real Rego: the reported misconfiguration."""
    statements = _expand([_BUILTIN_PROJECT_DENY], {}, project="")
    assert [(s["scope"], s.get("project")) for s in statements] == [("project", None)]
    result = _evaluate([allow_policy("allow-all", _WRITE), *statements], project=project)
    assert result["allow"] is False
    assert result["denied_by"] == _BUILTIN_PROJECT_DENY


def test_custom_global_policy_with_project_deny_on_a_global_assignment_blocks() -> None:
    policy = Policy(
        name="no-scripts",
        statements=[{"effect": "deny", "actions": _WRITE, "scope": "project", "conditions": _SCRIPT_ONLY}],
    )
    statements = _expand([policy.name], {policy.name: policy}, project="")
    assert "project" not in statements[0]
    result = _evaluate([allow_policy("allow-all", _WRITE), *statements])
    assert result["allow"] is False
    assert result["denied_by"] == "no-scripts"


# --- Nothing else got wider --------------------------------------------------


@pytest.mark.parametrize("project", ["payments", "other", ""])
@pytest.mark.parametrize("any_project", [False, True])
def test_unstamped_project_allow_grants_nothing(project: str, *, any_project: bool) -> None:
    """The fail-closed rule is for denies only: an unstamped allow stays inert."""
    allow = allow_policy("unstamped-allow", _WRITE, scope="project")
    result = _evaluate([allow], project=project, any_project=any_project)
    assert result["allow"] is False
    assert result["matched_policy"] == ""
    assert result["allowed_projects"] == []


def test_builtin_project_allow_on_a_global_assignment_grants_nothing() -> None:
    statements = _expand(["workflow:read:project"], {}, project="")
    assert "project" not in statements[0]
    result = _evaluate(statements, action="read", resource_type="workflow")
    assert result["allow"] is False


@_UNSTAMPED
@pytest.mark.parametrize(
    ("resource_type", "action"), [("workflow", "write"), ("workflow", "read"), ("step_type", "read")]
)
def test_unstamped_project_deny_leaves_other_actions_alone(stamp: str | None, resource_type: str, action: str) -> None:
    allow = allow_policy("allow-other", [f"{resource_type}:{action}"])
    result = _evaluate([allow, _unstamped_deny(stamp)], action=action, resource_type=resource_type)
    assert result["allow"] is True
    assert result["deny"] is False


@pytest.mark.parametrize("scope", ["own", "self"])
def test_unstamped_deny_in_other_scopes_is_not_broadened(scope: str) -> None:
    """Only ``scope: "project"`` fails closed; the API rejects these scopes for denies."""
    deny = deny_policy("odd-scope-deny", _WRITE, scope=scope)
    result = _evaluate([allow_policy("allow-all", _WRITE), deny])
    assert result["allow"] is True
    assert result["deny"] is False


@pytest.mark.parametrize(("project", "denied"), [("payments", True), ("other", False), ("", False)])
def test_stamped_project_deny_stays_in_its_project(project: str, *, denied: bool) -> None:
    statements = _expand([_BUILTIN_PROJECT_DENY], {}, project="payments")
    assert [(s["scope"], s["project"]) for s in statements] == [("project", "payments")]
    result = _evaluate([allow_policy("allow-all", _WRITE), *statements], project=project)
    assert result["deny"] is denied
    assert result["allow"] is not denied


def test_any_scope_deny_on_a_project_assignment_stays_in_its_project() -> None:
    """Project narrowing of ``any`` denies is what keeps the stamp meaningful."""
    statements = _expand(["step_type:write:any:deny:script"], {}, project="payments")
    assert [(s["scope"], s["project"]) for s in statements] == [("project", "payments")]
    assert _evaluate([allow_policy("allow-all", _WRITE), *statements], project="other")["allow"] is True
    assert _evaluate([allow_policy("allow-all", _WRITE), *statements], project="payments")["allow"] is False


# --- Pattern provenance is ignored by Rego -----------------------------------


@pytest.mark.parametrize("project", ["payments", "payroll", "sandbox", ""])
@pytest.mark.parametrize("any_project", [False, True])
def test_project_pattern_key_does_not_change_decisions(project: str, *, any_project: bool) -> None:
    """The resolver stamps ``project_pattern`` on pattern-sourced denies for audit only."""
    statements = _expand([_BUILTIN_PROJECT_DENY], {}, project="payments")
    with_key = [{**s, "project_pattern": "pay*"} for s in statements]
    allow = allow_policy("allow-all", _WRITE)
    plain = _evaluate([allow, *statements], project=project, any_project=any_project)
    tagged = _evaluate([allow, *with_key], project=project, any_project=any_project)
    keys = ("allow", "deny", "denial_reason", "denied_by", "matched_policy")
    assert {k: plain.get(k) for k in keys} == {k: tagged.get(k) for k in keys}
