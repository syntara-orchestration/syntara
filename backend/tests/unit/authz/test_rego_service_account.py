"""Authorization for independent service-account identities."""

import pytest

from syntara.authz.role_conventions import BUILTIN_POLICIES
from tests.unit.authz.conftest import build_opa_input, deny_policy, policies_for_role

SA_ACTIONS = sorted({p.action for p in BUILTIN_POLICIES if p.resource == "service_account"})


@pytest.mark.parametrize("action", SA_ACTIONS)
@pytest.mark.parametrize("role", ["admin", "authenticated", "auditor", "project-admin", "project-auditor"])
@pytest.mark.parametrize("is_creator", [False, True])
def test_account_management(opa_evaluate, action, role, is_creator):
    policies = policies_for_role(role)
    if role != "authenticated":
        policies += policies_for_role("authenticated")
    result = opa_evaluate(
        build_opa_input(
            action=action,
            resource_type="service_account",
            user_id="human",
            resource_metadata={"created_by": "human" if is_creator else "another-human"},
            effective_policies=policies,
        )
    )
    assert result["allow"] is (action in {"create", "read"} or role == "admin")


@pytest.mark.parametrize("action", SA_ACTIONS)
@pytest.mark.parametrize("role", ["project-admin", "project-auditor"])
@pytest.mark.parametrize("is_creator", [False, True])
def test_project_roles_alone_do_not_manage_accounts(opa_evaluate, action, role, is_creator):
    result = opa_evaluate(
        build_opa_input(
            action=action,
            resource_type="service_account",
            user_id="human",
            resource_metadata={"created_by": "human" if is_creator else "another-human"},
            effective_policies=policies_for_role(role),
        )
    )
    assert result["allow"] is False


@pytest.mark.parametrize("action", SA_ACTIONS)
def test_explicit_deny_overrides_authenticated_grants(opa_evaluate, action):
    result = opa_evaluate(
        build_opa_input(
            action=action,
            resource_type="service_account",
            user_id="human",
            resource_metadata={"created_by": "human"},
            effective_policies=[
                *policies_for_role("authenticated"),
                deny_policy("blocked", [f"service_account:{action}"]),
            ],
        )
    )
    assert result["allow"] is False
    assert result["denied_by"] == "blocked"
