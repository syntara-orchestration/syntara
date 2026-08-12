"""Unit tests for RoleService CRUD operations.

Tests cover:
- Create, read, list, update, delete operations
- Policy name validation on create/update
- Builtin protection
- Name conflict handling
- Policy names (JSONB column) management
"""

from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.exceptions import BuiltinProtectionError, RoleNameConflictError, RoleNotFoundError
from syntara.authz.models.assignments import RoleAssignment
from syntara.authz.models.role import Role
from syntara.authz.services.role_service import RoleService
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.models.group import Group

_P_READ = "workflow:read:any"
_P_WRITE = "workflow:create:any"
_P_DELETE = "workflow:delete:any"


@pytest.mark.asyncio
async def test_create_role(test_db_session: AsyncSession, test_user: User) -> None:
    """Create a custom role linked to policies."""
    svc = RoleService(test_db_session, test_user)
    role = await svc.create_role(
        name="reviewer",
        policies=[_P_READ, _P_WRITE],
        description="Review role",
        labels={"team": "qa"},
    )
    assert role.name == "reviewer"
    assert role.description == "Review role"
    assert role.is_builtin is False
    assert role.labels == {"team": "qa"}

    role_read = await svc.to_role_read(role)
    assert set(role_read.policies) == {_P_READ, _P_WRITE}


@pytest.mark.asyncio
async def test_create_role_with_unknown_policy(test_db_session: AsyncSession, test_user: User) -> None:
    """Creating a role with non-existent policy names raises SafeValueError."""
    svc = RoleService(test_db_session, test_user)
    with pytest.raises(SafeValueError, match="Policies not found"):
        await svc.create_role(name="bad-role", policies=["nonexistent:policy"])


@pytest.mark.asyncio
async def test_create_role_name_conflict(test_db_session: AsyncSession, test_user: User) -> None:
    """Duplicate name in the same scope raises RoleNameConflictError."""
    svc = RoleService(test_db_session, test_user)
    await svc.create_role(name="dup-role", policies=[_P_READ])
    with pytest.raises(RoleNameConflictError):
        await svc.create_role(name="dup-role", policies=[_P_READ])


@pytest.mark.asyncio
async def test_get_role(test_db_session: AsyncSession, test_user: User) -> None:
    """Get a role by ID."""
    svc = RoleService(test_db_session, test_user)
    created = await svc.create_role(name="get-role", policies=[_P_READ])
    fetched = await svc.get_role(created.id)
    assert fetched.id == created.id
    assert fetched.name == "get-role"


@pytest.mark.asyncio
async def test_get_role_not_found(test_db_session: AsyncSession, test_user: User) -> None:
    """Getting a non-existent role raises RoleNotFoundError."""
    svc = RoleService(test_db_session, test_user)
    with pytest.raises(RoleNotFoundError):
        await svc.get_role(uuid4())


@pytest.mark.asyncio
async def test_list_roles(test_db_session: AsyncSession, test_user: User) -> None:
    """List roles returns created roles with resolved policies."""
    svc = RoleService(test_db_session, test_user)
    await svc.create_role(name="list-r1", policies=[_P_READ])
    await svc.create_role(name="list-r2", policies=[_P_WRITE])
    result = await svc.list_roles(limit=100, include_total=True)
    names = [r.name for r in result.resources]
    assert "list-r1" in names
    assert "list-r2" in names
    r1 = next(r for r in result.resources if r.name == "list-r1")
    assert _P_READ in r1.policies


@pytest.mark.asyncio
async def test_update_role(test_db_session: AsyncSession, test_user: User) -> None:
    """Update name, description, policies, and labels of a custom role."""
    svc = RoleService(test_db_session, test_user)
    role = await svc.create_role(
        name="updatable-role",
        policies=[_P_READ],
        description="original",
    )
    updated = await svc.update_role(
        role.id,
        name="renamed-role",
        description="updated desc",
        policies=[_P_WRITE, _P_DELETE],
        labels={"updated": "true"},
    )
    assert updated.name == "renamed-role"
    assert updated.description == "updated desc"
    assert updated.labels == {"updated": "true"}

    role_read = await svc.to_role_read(updated)
    assert set(role_read.policies) == {_P_WRITE, _P_DELETE}


@pytest.mark.asyncio
async def test_update_role_partial(test_db_session: AsyncSession, test_user: User) -> None:
    """Partial update only changes provided fields."""
    svc = RoleService(test_db_session, test_user)
    role = await svc.create_role(name="partial-role", policies=[_P_READ], description="original")
    updated = await svc.update_role(role.id, description="only desc changed")
    assert updated.name == "partial-role"
    assert updated.description == "only desc changed"
    role_read = await svc.to_role_read(updated)
    assert _P_READ in role_read.policies


@pytest.mark.asyncio
async def test_update_builtin_role_rejected(test_db_session: AsyncSession, test_user: User) -> None:
    """Cannot update a builtin role."""
    builtin = Role(name="builtin-test-role", is_builtin=True, labels={})
    test_db_session.add(builtin)
    await test_db_session.commit()
    await test_db_session.refresh(builtin)

    svc = RoleService(test_db_session, test_user)
    with pytest.raises(BuiltinProtectionError):
        await svc.update_role(builtin.id, description="hacked")


@pytest.mark.asyncio
async def test_rename_role_updates_assignments(test_db_session: AsyncSession, test_user: User) -> None:
    """Renaming a role propagates the new name to all assignments."""
    svc = RoleService(test_db_session, test_user)
    role = await svc.create_role(name="old-role-name", policies=[_P_READ])

    user_id = test_user.id
    user_assign = RoleAssignment(principal_id=user_id, role_name="old-role-name")
    test_db_session.add(user_assign)

    group = Group(name="rename-test-grp", description="", labels={})
    test_db_session.add(group)
    await test_db_session.flush()

    group_assign = RoleAssignment(group_id=group.id, role_name="old-role-name")
    test_db_session.add(group_assign)
    await test_db_session.commit()
    ua_id = user_assign.id
    ga_id = group_assign.id

    await svc.update_role(role.id, name="new-role-name")

    test_db_session.expire_all()
    ua = (await test_db_session.exec(select(RoleAssignment).where(RoleAssignment.id == ua_id))).first()
    assert ua is not None
    assert ua.role_name == "new-role-name"

    ga = (await test_db_session.exec(select(RoleAssignment).where(RoleAssignment.id == ga_id))).first()
    assert ga is not None
    assert ga.role_name == "new-role-name"


@pytest.mark.asyncio
async def test_update_role_name_conflict(test_db_session: AsyncSession, test_user: User) -> None:
    """Renaming to an existing name raises RoleNameConflictError."""
    svc = RoleService(test_db_session, test_user)
    await svc.create_role(name="existing-role", policies=[_P_READ])
    r2 = await svc.create_role(name="other-role", policies=[_P_READ])
    with pytest.raises(RoleNameConflictError):
        await svc.update_role(r2.id, name="existing-role")


@pytest.mark.asyncio
async def test_delete_role(test_db_session: AsyncSession, test_user: User) -> None:
    """Delete a custom role and its references."""
    svc = RoleService(test_db_session, test_user)
    role = await svc.create_role(name="deletable-role", policies=[_P_READ])
    await svc.delete_role(role.id)
    with pytest.raises(RoleNotFoundError):
        await svc.get_role(role.id)


@pytest.mark.asyncio
async def test_delete_builtin_role_rejected(test_db_session: AsyncSession, test_user: User) -> None:
    """Cannot delete a builtin role."""
    builtin = Role(name="builtin-del-role", is_builtin=True, labels={})
    test_db_session.add(builtin)
    await test_db_session.commit()
    await test_db_session.refresh(builtin)

    svc = RoleService(test_db_session, test_user)
    with pytest.raises(BuiltinProtectionError):
        await svc.delete_role(builtin.id)


@pytest.mark.asyncio
async def test_create_role_empty_policies(test_db_session: AsyncSession, test_user: User) -> None:
    """Create a role with no policies."""
    svc = RoleService(test_db_session, test_user)
    role = await svc.create_role(name="empty-role", policies=[])
    assert role.name == "empty-role"
    role_read = await svc.to_role_read(role)
    assert role_read.policies == []


@pytest.mark.asyncio
async def test_name_conflict_scoped_to_project(test_db_session: AsyncSession, test_user: User) -> None:
    """Same name in different project scopes is allowed."""
    from syntara.authz.models.project import Project

    project = Project(name="role-scope-proj", labels={})
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)

    svc = RoleService(test_db_session, test_user)
    await svc.create_role(name="scoped-role", policies=["workflow:read:project"], project_id=project.id)
    global_role = await svc.create_role(name="scoped-role", policies=[_P_READ])
    assert global_role.name == "scoped-role"
    assert global_role.project_id is None


# ============================================================================
# Policy scope validation on role create/update
# ============================================================================


@pytest.mark.asyncio
async def test_project_role_rejects_global_policy(test_db_session: AsyncSession, test_user: User) -> None:
    """A project-scoped role cannot reference a global policy."""
    from syntara.authz.models.policy import Policy
    from syntara.authz.models.project import Project

    project = Project(name="scope-test-proj", labels={})
    test_db_session.add(project)
    await test_db_session.flush()

    global_policy = Policy(
        name="global-only-policy",
        statements=[{"name": "global-only-policy", "effect": "allow", "actions": ["test:read"], "scope": "any"}],
        is_builtin=False,
        project_id=None,
        labels={},
    )
    test_db_session.add(global_policy)
    await test_db_session.commit()

    svc = RoleService(test_db_session, test_user)
    with pytest.raises(SafeValueError, match="Policies not found in project"):
        await svc.create_role(name="bad-role", policies=["global-only-policy"], project_id=project.id)


@pytest.mark.asyncio
async def test_project_role_rejects_other_project_policy(test_db_session: AsyncSession, test_user: User) -> None:
    """A project-scoped role cannot reference a policy from a different project."""
    from syntara.authz.models.policy import Policy
    from syntara.authz.models.project import Project

    proj_a = Project(name="proj-a", labels={})
    proj_b = Project(name="proj-b", labels={})
    test_db_session.add_all([proj_a, proj_b])
    await test_db_session.flush()

    policy_a = Policy(
        name="shared-name",
        statements=[{"name": "shared-name", "effect": "allow", "actions": ["cred:read"], "scope": "any"}],
        is_builtin=False,
        project_id=proj_a.id,
        labels={},
    )
    test_db_session.add(policy_a)
    await test_db_session.commit()

    svc = RoleService(test_db_session, test_user)
    with pytest.raises(SafeValueError, match="Policies not found in project"):
        await svc.create_role(name="cross-proj-role", policies=["shared-name"], project_id=proj_b.id)


@pytest.mark.asyncio
async def test_project_role_accepts_same_project_policy(test_db_session: AsyncSession, test_user: User) -> None:
    """A project-scoped role can reference a policy from the same project."""
    from syntara.authz.models.policy import Policy
    from syntara.authz.models.project import Project

    project = Project(name="same-proj", labels={})
    test_db_session.add(project)
    await test_db_session.flush()

    policy = Policy(
        name="proj-policy",
        statements=[{"name": "proj-policy", "effect": "allow", "actions": ["test:read"], "scope": "any"}],
        is_builtin=False,
        project_id=project.id,
        labels={},
    )
    test_db_session.add(policy)
    await test_db_session.commit()

    svc = RoleService(test_db_session, test_user)
    role = await svc.create_role(name="same-proj-role", policies=["proj-policy"], project_id=project.id)
    assert role.policy_names == ["proj-policy"]


@pytest.mark.asyncio
async def test_global_role_rejects_project_policy(test_db_session: AsyncSession, test_user: User) -> None:
    """A system-scoped role cannot reference a project-scoped policy."""
    from syntara.authz.models.policy import Policy
    from syntara.authz.models.project import Project

    project = Project(name="proj-for-global-test", labels={})
    test_db_session.add(project)
    await test_db_session.flush()

    policy = Policy(
        name="proj-scoped-policy",
        statements=[{"name": "proj-scoped-policy", "effect": "allow", "actions": ["test:read"], "scope": "any"}],
        is_builtin=False,
        project_id=project.id,
        labels={},
    )
    test_db_session.add(policy)
    await test_db_session.commit()

    svc = RoleService(test_db_session, test_user)
    with pytest.raises(SafeValueError, match="Policies not found in global scope"):
        await svc.create_role(name="sys-role", policies=["proj-scoped-policy"])


@pytest.mark.asyncio
async def test_update_role_rejects_cross_project_policy(test_db_session: AsyncSession, test_user: User) -> None:
    """Updating a project role to reference another project's policy is rejected."""
    from syntara.authz.models.policy import Policy
    from syntara.authz.models.project import Project

    proj_a = Project(name="update-proj-a", labels={})
    proj_b = Project(name="update-proj-b", labels={})
    test_db_session.add_all([proj_a, proj_b])
    await test_db_session.flush()

    policy_a = Policy(
        name="update-policy-a",
        statements=[{"name": "update-policy-a", "effect": "allow", "actions": ["test:read"], "scope": "any"}],
        is_builtin=False,
        project_id=proj_a.id,
        labels={},
    )
    policy_b = Policy(
        name="update-policy-b",
        statements=[{"name": "update-policy-b", "effect": "allow", "actions": ["test:read"], "scope": "any"}],
        is_builtin=False,
        project_id=proj_b.id,
        labels={},
    )
    test_db_session.add_all([policy_a, policy_b])
    await test_db_session.commit()

    svc = RoleService(test_db_session, test_user)
    role = await svc.create_role(name="update-test-role", policies=["update-policy-a"], project_id=proj_a.id)

    with pytest.raises(SafeValueError, match="Policies not found in project"):
        await svc.update_role(role.id, policies=["update-policy-b"])


# ============================================================================
# Builtin policy scope validation
# ============================================================================


@pytest.mark.asyncio
async def test_system_role_rejects_project_scoped_builtin(test_db_session: AsyncSession, test_user: User) -> None:
    """A system-scoped role cannot reference a project-scoped builtin policy."""
    svc = RoleService(test_db_session, test_user)
    with pytest.raises(SafeValueError, match="Policies not available in global scope"):
        await svc.create_role(name="bad-sys-role", policies=["policy:update:project"])


@pytest.mark.asyncio
async def test_project_role_rejects_system_scoped_builtin(test_db_session: AsyncSession, test_user: User) -> None:
    """A project-scoped role cannot reference a system-scoped builtin policy."""
    from syntara.authz.models.project import Project

    project = Project(name="builtin-scope-proj", labels={})
    test_db_session.add(project)
    await test_db_session.commit()

    svc = RoleService(test_db_session, test_user)
    with pytest.raises(SafeValueError, match="Policies not available in project"):
        await svc.create_role(name="bad-proj-role", policies=["policy:update:any"], project_id=project.id)
