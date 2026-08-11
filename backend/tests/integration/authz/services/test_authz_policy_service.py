"""Unit tests for PolicyService CRUD operations.

Tests cover:
- Create, read, list, update, delete operations
- Name conflict detection
- Builtin protection
- Not-found error handling
"""

from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.exceptions import (
    BuiltinProtectionError,
    InvalidResourceActionError,
    PolicyNameConflictError,
    PolicyNotFoundError,
)
from syntara.authz.models.policy import Policy
from syntara.authz.models.role import Role
from syntara.authz.services.policy_service import PolicyService
from syntara.core.models import User


@pytest.mark.asyncio
async def test_create_policy(test_db_session: AsyncSession, test_user: User) -> None:
    """Create a custom policy with statements."""
    svc = PolicyService(test_db_session, test_user)
    policy = await svc.create_policy(
        name="test-policy",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
        description="A test policy",
        labels={"env": "test"},
    )
    assert policy.name == "test-policy"
    assert policy.description == "A test policy"
    assert policy.is_builtin is False
    assert policy.labels == {"env": "test"}
    assert len(policy.statements) == 1


@pytest.mark.asyncio
async def test_create_policy_without_optional_fields(test_db_session: AsyncSession, test_user: User) -> None:
    """Create a policy with only required fields."""
    svc = PolicyService(test_db_session, test_user)
    policy = await svc.create_policy(
        name="minimal-policy",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
    )
    assert policy.name == "minimal-policy"
    assert policy.description is None
    assert policy.labels == {}


@pytest.mark.asyncio
async def test_create_policy_name_conflict(test_db_session: AsyncSession, test_user: User) -> None:
    """Duplicate name in the same scope raises PolicyNameConflictError."""
    svc = PolicyService(test_db_session, test_user)
    await svc.create_policy(
        name="dup-policy",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
    )
    with pytest.raises(PolicyNameConflictError):
        await svc.create_policy(
            name="dup-policy",
            statements=[{"effect": "allow", "actions": ["setting:write"], "scope": "any"}],
        )


@pytest.mark.asyncio
async def test_get_policy(test_db_session: AsyncSession, test_user: User) -> None:
    """Get a policy by ID."""
    svc = PolicyService(test_db_session, test_user)
    created = await svc.create_policy(
        name="get-me",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
    )
    fetched = await svc.get_policy(created.id)
    assert fetched.id == created.id
    assert fetched.name == "get-me"


@pytest.mark.asyncio
async def test_get_policy_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Getting a non-existent policy raises PolicyNotFoundError."""
    svc = PolicyService(test_db_session, test_user)
    with pytest.raises(PolicyNotFoundError):
        await svc.get_policy(uuid4())


@pytest.mark.asyncio
async def test_list_policies(test_db_session: AsyncSession, test_user: User) -> None:
    """List policies returns created policies."""
    svc = PolicyService(test_db_session, test_user)
    await svc.create_policy(
        name="list-p1", statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}]
    )
    await svc.create_policy(
        name="list-p2", statements=[{"effect": "allow", "actions": ["setting:write"], "scope": "any"}]
    )
    result = await svc.list_policies(limit=200, include_total=True)
    names = [r.name for r in result.resources]
    assert "list-p1" in names
    assert "list-p2" in names


@pytest.mark.asyncio
async def test_update_policy(test_db_session: AsyncSession, test_user: User) -> None:
    """Update name, description, statements, and labels of a custom policy."""
    svc = PolicyService(test_db_session, test_user)
    policy = await svc.create_policy(
        name="updatable",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
        description="original",
    )
    updated = await svc.update_policy(
        policy.id,
        name="renamed",
        description="updated desc",
        statements=[{"effect": "allow", "actions": ["workflow:delete"], "scope": "any"}],
        labels={"updated": "true"},
    )
    assert updated.name == "renamed"
    assert updated.description == "updated desc"
    assert updated.statements == [{"effect": "allow", "actions": ["workflow:delete"], "scope": "any"}]
    assert updated.labels == {"updated": "true"}


@pytest.mark.asyncio
async def test_update_policy_partial(test_db_session: AsyncSession, test_user: User) -> None:
    """Partial update only changes provided fields."""
    svc = PolicyService(test_db_session, test_user)
    policy = await svc.create_policy(
        name="partial-update",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
        description="original",
    )
    updated = await svc.update_policy(policy.id, description="only desc changed")
    assert updated.name == "partial-update"
    assert updated.description == "only desc changed"


@pytest.mark.asyncio
async def test_update_builtin_policy_rejected(test_db_session: AsyncSession, test_user: User) -> None:
    """Cannot update a builtin policy."""
    builtin = Policy(
        name="builtin-policy",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
        is_builtin=True,
        labels={},
    )
    test_db_session.add(builtin)
    await test_db_session.commit()
    await test_db_session.refresh(builtin)

    svc = PolicyService(test_db_session, test_user)
    with pytest.raises(BuiltinProtectionError):
        await svc.update_policy(builtin.id, description="hacked")


@pytest.mark.asyncio
async def test_rename_policy_updates_roles(test_db_session: AsyncSession, test_user: User) -> None:
    """Renaming a policy propagates the new name to all roles that reference it."""
    svc = PolicyService(test_db_session, test_user)
    policy = await svc.create_policy(
        name="old-policy-name",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
    )

    role = Role(
        name="refs-policy",
        is_builtin=False,
        scope="system",
        policy_names=["old-policy-name", "workflow:read"],
        labels={},
    )
    test_db_session.add(role)
    await test_db_session.commit()
    role_id = role.id

    await svc.update_policy(policy.id, name="new-policy-name")

    test_db_session.expire_all()
    updated_role = (await test_db_session.exec(select(Role).where(Role.id == role_id))).first()
    assert updated_role is not None
    assert "new-policy-name" in updated_role.policy_names
    assert "old-policy-name" not in updated_role.policy_names
    assert "workflow:read" in updated_role.policy_names


@pytest.mark.asyncio
async def test_update_policy_name_conflict(test_db_session: AsyncSession, test_user: User) -> None:
    """Renaming to an existing name raises PolicyNameConflictError."""
    svc = PolicyService(test_db_session, test_user)
    await svc.create_policy(
        name="existing-name", statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}]
    )
    p2 = await svc.create_policy(
        name="other-name", statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}]
    )
    with pytest.raises(PolicyNameConflictError):
        await svc.update_policy(p2.id, name="existing-name")


@pytest.mark.asyncio
async def test_delete_policy(test_db_session: AsyncSession, test_user: User) -> None:
    """Delete a custom policy."""
    svc = PolicyService(test_db_session, test_user)
    policy = await svc.create_policy(
        name="deletable",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
    )
    await svc.delete_policy(policy.id)
    with pytest.raises(PolicyNotFoundError):
        await svc.get_policy(policy.id)


@pytest.mark.asyncio
async def test_delete_builtin_policy_rejected(test_db_session: AsyncSession, test_user: User) -> None:
    """Cannot delete a builtin policy."""
    builtin = Policy(
        name="builtin-delete-test",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
        is_builtin=True,
        labels={},
    )
    test_db_session.add(builtin)
    await test_db_session.commit()
    await test_db_session.refresh(builtin)

    svc = PolicyService(test_db_session, test_user)
    with pytest.raises(BuiltinProtectionError):
        await svc.delete_policy(builtin.id)


@pytest.mark.asyncio
async def test_name_conflict_scoped_to_project(test_db_session: AsyncSession, test_user: User) -> None:
    """Same name in different project scopes is allowed."""
    from syntara.authz.models.project import Project

    project = Project(name="scope-test-proj", labels={})
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)

    svc = PolicyService(test_db_session, test_user)
    await svc.create_policy(
        name="scoped-policy",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "project"}],
        project_id=project.id,
    )
    # Same name but global scope -- should succeed
    global_policy = await svc.create_policy(
        name="scoped-policy",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
    )
    assert global_policy.name == "scoped-policy"
    assert global_policy.project_id is None


# ============================================================================
# Project Policy Validation (AAP-74594)
# ============================================================================


@pytest.fixture(autouse=True, scope="module")
def _ensure_project_eligible() -> None:
    """Ensure the project-eligible registry includes types used in these tests.

    The unit conftest builds the registry from discovered routes, but import
    ordering in CI can leave _project_eligible under-populated.  Patch it
    once for the module so project-validation tests are deterministic.
    """
    import syntara.authz.resource_actions as ra

    needed = {"workflow", "execution", "project"}
    if not needed.issubset(ra._project_eligible):
        ra._project_eligible = ra._project_eligible | frozenset(needed)


@pytest.mark.asyncio
async def test_create_project_policy_rejects_scope_any(test_db_session: AsyncSession, test_user: User) -> None:
    """scope=any is invalid at project scope — must be 'project'."""
    from syntara.authz.models.project import Project

    project = Project(name="val-proj-1", labels={})
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)

    svc = PolicyService(test_db_session, test_user)
    with pytest.raises(InvalidResourceActionError, match=r"scope='project'.*got scope='any'"):
        await svc.create_policy(
            name="bad-scope-any",
            statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
            project_id=project.id,
        )


@pytest.mark.asyncio
async def test_create_project_policy_rejects_scope_self(test_db_session: AsyncSession, test_user: User) -> None:
    """scope=self for non-user resources is invalid at project scope."""
    from syntara.authz.models.project import Project

    project = Project(name="val-proj-2", labels={})
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)

    svc = PolicyService(test_db_session, test_user)
    with pytest.raises(InvalidResourceActionError, match=r"scope='project'.*got scope='self'"):
        await svc.create_policy(
            name="bad-scope-self",
            statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "self"}],
            project_id=project.id,
        )


@pytest.mark.asyncio
async def test_create_project_policy_rejects_system_resource(test_db_session: AsyncSession, test_user: User) -> None:
    """System-only resource types (user, setting, group) are invalid at project scope."""
    from syntara.authz.models.project import Project

    project = Project(name="val-proj-3", labels={})
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)

    svc = PolicyService(test_db_session, test_user)
    for action in ["user:read", "setting:write", "group:create", "user:*"]:
        with pytest.raises(InvalidResourceActionError, match="not valid at project scope"):
            await svc.create_policy(
                name=f"bad-{action.replace(':', '-').replace('*', 'wild')}",
                statements=[{"effect": "allow", "actions": [action], "scope": "project"}],
                project_id=project.id,
            )


@pytest.mark.asyncio
async def test_create_project_policy_accepts_valid(test_db_session: AsyncSession, test_user: User) -> None:
    """Valid project policy with scope=project and eligible resource types succeeds."""
    from syntara.authz.models.project import Project

    project = Project(name="val-proj-4", labels={})
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)

    svc = PolicyService(test_db_session, test_user)
    policy = await svc.create_policy(
        name="valid-project-policy",
        statements=[
            {"effect": "allow", "actions": ["workflow:read", "execution:run"], "scope": "project"},
        ],
        project_id=project.id,
    )
    assert policy.project_id == project.id
    assert policy.scope == "project"


@pytest.mark.asyncio
async def test_update_project_policy_rejects_invalid_scope(test_db_session: AsyncSession, test_user: User) -> None:
    """Updating a project policy with scope=any is rejected."""
    from syntara.authz.models.project import Project

    project = Project(name="val-proj-5", labels={})
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)

    svc = PolicyService(test_db_session, test_user)
    policy = await svc.create_policy(
        name="update-target",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "project"}],
        project_id=project.id,
    )

    with pytest.raises(InvalidResourceActionError, match=r"scope='project'.*got scope='any'"):
        await svc.update_policy(
            policy_id=policy.id,
            statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
        )


@pytest.mark.asyncio
async def test_create_project_policy_wildcard_eligible(test_db_session: AsyncSession, test_user: User) -> None:
    """Wildcard actions like workflow:* are validated against eligible resource types."""
    from syntara.authz.models.project import Project

    project = Project(name="val-proj-6", labels={})
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)

    svc = PolicyService(test_db_session, test_user)

    # workflow:* should succeed — workflow is project-eligible
    policy = await svc.create_policy(
        name="wildcard-eligible",
        statements=[{"effect": "allow", "actions": ["workflow:*"], "scope": "project"}],
        project_id=project.id,
    )
    assert policy.project_id == project.id

    # user:* should fail — user is not project-eligible
    with pytest.raises(InvalidResourceActionError, match="not valid at project scope"):
        await svc.create_policy(
            name="wildcard-ineligible",
            statements=[{"effect": "allow", "actions": ["user:*"], "scope": "project"}],
            project_id=project.id,
        )


# ---------------------------------------------------------------------------
# Deny-effect rejection (AAP-74620)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_deny_policy_rejected(test_db_session: AsyncSession, test_user: User) -> None:
    """Deny-effect policies are not supported and must be rejected."""
    from syntara.authz.exceptions import DenyEffectNotSupportedError

    svc = PolicyService(test_db_session, test_user)
    with pytest.raises(DenyEffectNotSupportedError, match="not supported"):
        await svc.create_policy(
            name="deny-workflow-read",
            statements=[{"effect": "deny", "actions": ["workflow:read"], "scope": "any"}],
        )


@pytest.mark.asyncio
async def test_create_deny_policy_rejected_project_scoped(test_db_session: AsyncSession, test_user: User) -> None:
    """Project-scoped deny-effect policies are also rejected."""
    from syntara.authz.exceptions import DenyEffectNotSupportedError
    from syntara.authz.models.project import Project

    project = Project(name="deny-proj-1", labels={})
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)

    svc = PolicyService(test_db_session, test_user)
    with pytest.raises(DenyEffectNotSupportedError, match="not supported"):
        await svc.create_policy(
            name="deny-wf-read-proj",
            statements=[{"effect": "deny", "actions": ["workflow:read"], "scope": "project"}],
            project_id=project.id,
        )


@pytest.mark.asyncio
async def test_update_policy_to_deny_rejected(test_db_session: AsyncSession, test_user: User) -> None:
    """Updating a policy to add deny-effect statements is rejected."""
    from syntara.authz.exceptions import DenyEffectNotSupportedError

    svc = PolicyService(test_db_session, test_user)
    policy = await svc.create_policy(
        name="allow-then-deny",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
    )

    with pytest.raises(DenyEffectNotSupportedError, match="not supported"):
        await svc.update_policy(
            policy_id=policy.id,
            statements=[{"effect": "deny", "actions": ["workflow:read"], "scope": "any"}],
        )


@pytest.mark.asyncio
async def test_create_allow_policy_unaffected(test_db_session: AsyncSession, test_user: User) -> None:
    """Allow-effect policies are unaffected by the deny restriction."""
    svc = PolicyService(test_db_session, test_user)
    policy = await svc.create_policy(
        name="allow-still-works",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
    )
    assert policy.name == "allow-still-works"
    assert policy.statements[0]["effect"] == "allow"
