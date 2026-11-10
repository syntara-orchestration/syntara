"""The authenticated baseline allows all step kinds; scoped denies override it."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.exceptions import BuiltinProtectionError
from syntara.authz.role_conventions import (
    BUILTIN_POLICIES,
    PolicyInfo,
    builtin_policy_uuid,
    get_builtin_policy,
    resolve_builtin_policy_statements,
)
from syntara.authz.schemas import PolicyStatementSchema
from syntara.authz.services.policy_service import PolicyService
from syntara.core.models import User
from syntara.workflows.node_kinds import NODE_KINDS
from tests.unit.authz.conftest import allow_policy, build_opa_input

DENY_POLICIES = [p for p in BUILTIN_POLICIES if p.resource == "step_type" and p.effect == "deny"]


def test_catalog_covers_exactly_the_grantable_kinds_and_scopes() -> None:
    """New grantable kinds automatically get both variants, with no implicit denies."""
    assert {(p.kind, p.scope) for p in DENY_POLICIES} == {
        (kind, scope) for kind in NODE_KINDS for scope in ("any", "project")
    }
    assert len(DENY_POLICIES) == 2 * len(NODE_KINDS)
    assert {p.name for p in DENY_POLICIES} == {
        f"step_type:write:{scope}:deny:{kind}" for kind in NODE_KINDS for scope in ("any", "project")
    }
    assert all(not p.roles for p in DENY_POLICIES)
    assert all(p.kind != "internal_activity" for p in DENY_POLICIES)


@pytest.mark.parametrize("policy", [p for p in BUILTIN_POLICIES if p.resource == "step_type"], ids=lambda p: p.name)
def test_catalog_passes_api_and_service_validation(policy: PolicyInfo) -> None:
    """The registry uses the same statement contract accepted by policy CRUD."""
    assert get_builtin_policy(policy.name) == policy
    assert PolicyInfo.from_name(policy.name) == policy
    for statement in policy.statements:
        PolicyStatementSchema.model_validate(statement)
    PolicyService._validate_deny_effect(policy.statements)
    PolicyService._validate_resource_actions(policy.statements)
    if policy.scope == "project":
        PolicyService._validate_project_statements(policy.statements)


@pytest.mark.parametrize("policy", DENY_POLICIES, ids=lambda p: p.name)
def test_catalog_denies_only_the_matching_kind_and_project(
    policy: PolicyInfo, opa_evaluate: Callable[[dict[str, Any]], dict[str, Any]]
) -> None:
    """Evaluate the actual catalog statements against the production Rego policy."""
    assert policy.kind is not None
    statements = resolve_builtin_policy_statements(policy.name)
    deny = {**statements[0], "name": policy.name}
    if policy.scope == "project":
        deny["project"] = "payments"
    other_kind = next(kind for kind in sorted(NODE_KINDS) if kind != policy.kind)
    for kind, project, denied in (
        (policy.kind, "payments", True),
        (other_kind, "payments", False),
        (policy.kind, "other", policy.scope == "any"),
    ):
        result = opa_evaluate(
            build_opa_input(
                action="write",
                resource_type="step_type",
                resource_labels={"kind": kind},
                resource_project=project,
                effective_policies=[allow_policy("custom-step-allow", ["step_type:write"]), deny],
            )
        )
        assert result["deny"] is denied
        assert result["allow"] is not denied


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["step_type:write:any:deny:script", "step_type:write:project:deny:script"])
async def test_builtin_step_policy_can_be_read_but_not_modified(name: str) -> None:
    """Step policies use the existing UUID lookup, filtering, and builtin protection."""
    service = PolicyService(AsyncMock(spec=AsyncSession), User(username="admin"))
    policy_id = builtin_policy_uuid(name)
    policy = await service.get_policy_or_builtin(policy_id)
    assert policy.is_builtin
    assert policy.scope == name.split(":")[2]
    assert policy in service._filter_builtin_policies({}, scope_filter=policy.scope)
    with pytest.raises(BuiltinProtectionError):
        await service.update_policy(policy_id, description="changed")
    with pytest.raises(BuiltinProtectionError):
        await service.delete_policy(policy_id)


def test_no_builtin_policy_grants_step_authoring() -> None:
    """Removing the editable baseline must make deny-by-default reachable."""
    assert not any(p.resource == "step_type" and p.effect == "allow" for p in BUILTIN_POLICIES)
