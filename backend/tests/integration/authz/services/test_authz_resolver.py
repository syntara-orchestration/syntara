"""Unit tests for the authz policy resolver.

Tests cover:
- resolve_effective_policies() with global and project-scoped roles
- resolve_user_groups() for group membership resolution
- get_user_group_ids() implicit authenticated group inclusion
- _resolve_roles_to_policies() deduplication and project scoping
"""

from uuid import uuid4

import pytest
from sqlalchemy import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models.assignments import RoleAssignment
from syntara.authz.models.policy import Policy
from syntara.authz.models.project import Project
from syntara.authz.models.role import Role
from syntara.authz.resolver import (
    _resolve_roles_to_policies,
    get_user_group_ids,
    resolve_effective_policies,
    resolve_user_groups,
)
from syntara.authz.seed import seed_authz_data
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups
from syntara.service_accounts.models.service_account import ServiceAccount


@pytest.fixture
async def seeded_db(test_db_session: AsyncSession) -> AsyncSession:
    """Seed authz data and return the session."""
    await seed_authz_data(test_db_session)
    return test_db_session


# ============================================================================
# get_user_group_ids
# ============================================================================


@pytest.mark.asyncio
async def testget_user_group_ids_includes_authenticated(seeded_db: AsyncSession, test_user: User) -> None:
    """All users belong to the 'authenticated' group."""
    group_ids = await get_user_group_ids(seeded_db, test_user.id)
    # Find the authenticated group
    result = await seeded_db.exec(select(Group).where(Group.name == "authenticated"))
    auth_group = result.first()
    assert auth_group is not None
    assert auth_group.id in group_ids


@pytest.mark.asyncio
async def testget_user_group_ids_includes_explicit_groups(seeded_db: AsyncSession, test_user: User) -> None:
    """User's explicit group memberships are included."""
    custom_group = Group(id=uuid4(), name="custom-grp", description="", labels={})
    seeded_db.add(custom_group)
    await seeded_db.flush()
    await seeded_db.exec(insert(user_groups).values(user_id=test_user.id, group_id=custom_group.id))
    await seeded_db.commit()

    group_ids = await get_user_group_ids(seeded_db, test_user.id)
    assert custom_group.id in group_ids


@pytest.mark.asyncio
async def testget_user_group_ids_excludes_soft_deleted_groups(seeded_db: AsyncSession, test_user: User) -> None:
    """Soft-deleted groups must not appear in user's group IDs."""
    group = Group(id=uuid4(), name="soon-deleted-grp", description="", labels={})
    seeded_db.add(group)
    await seeded_db.flush()
    await seeded_db.exec(insert(user_groups).values(user_id=test_user.id, group_id=group.id))
    await seeded_db.commit()

    # Before soft-delete the group is present
    group_ids = await get_user_group_ids(seeded_db, test_user.id)
    assert group.id in group_ids

    # Soft-delete the group
    group.soft_delete(user_id=test_user.id)
    seeded_db.add(group)
    await seeded_db.commit()

    group_ids = await get_user_group_ids(seeded_db, test_user.id)
    assert group.id not in group_ids


@pytest.mark.asyncio
async def test_soft_deleted_group_policies_not_resolved(seeded_db: AsyncSession, test_user: User) -> None:
    """Soft-deleted group's role assignments must not grant policies to the user."""
    # Create policy, role, group, and wire them together
    policy = Policy(
        name="deleted-grp:test:any",
        statements=[{"name": "deleted-grp:test:any", "effect": "allow", "actions": ["secret-action"], "scope": "any"}],
        is_builtin=False,
        labels={},
    )
    seeded_db.add(policy)
    await seeded_db.flush()

    role = Role(name="deleted-grp-role", is_builtin=False, labels={}, policy_names=["deleted-grp:test:any"])
    seeded_db.add(role)
    await seeded_db.flush()

    group = Group(id=uuid4(), name="will-be-deleted-grp", description="", labels={})
    seeded_db.add(group)
    await seeded_db.flush()

    seeded_db.add(RoleAssignment(group_id=group.id, role_name=role.name))
    await seeded_db.exec(insert(user_groups).values(user_id=test_user.id, group_id=group.id))
    await seeded_db.commit()

    # User should have the policy before soft-delete
    policies = await resolve_effective_policies(seeded_db, test_user.id)
    assert "deleted-grp:test:any" in {p["name"] for p in policies}

    # Soft-delete the group
    group.soft_delete(user_id=test_user.id)
    seeded_db.add(group)
    await seeded_db.commit()

    # User should no longer have the policy
    policies = await resolve_effective_policies(seeded_db, test_user.id)
    assert "deleted-grp:test:any" not in {p["name"] for p in policies}


# ============================================================================
# _resolve_roles_to_policies
# ============================================================================


@pytest.mark.asyncio
async def test_resolve_roles_to_policies_empty(seeded_db: AsyncSession) -> None:
    """Empty role_names produces no policies."""
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    await _resolve_roles_to_policies(seeded_db, [], seen, result)
    assert result == []


@pytest.mark.asyncio
async def test_resolve_roles_to_policies_with_project(seeded_db: AsyncSession) -> None:
    """Project parameter narrows scope to project but preserves self scope."""
    # Create a policy and role with policy_names referencing it
    policy = Policy(
        name="test:resolve:any",
        statements=[{"name": "test:resolve:any", "effect": "allow", "actions": ["read"], "scope": "any"}],
        is_builtin=False,
        labels={},
    )
    seeded_db.add(policy)
    await seeded_db.flush()

    role = Role(name="resolve-test-role", is_builtin=False, policy_names=["test:resolve:any"], labels={})
    seeded_db.add(role)
    await seeded_db.commit()

    seen: set[str] = set()
    result: list[dict[str, object]] = []
    await _resolve_roles_to_policies(seeded_db, ["resolve-test-role"], seen, result, project="my-project")

    assert len(result) >= 1
    proj_stmts = [s for s in result if s.get("project") == "my-project"]
    assert len(proj_stmts) >= 1
    assert proj_stmts[0]["scope"] == "project"


@pytest.mark.asyncio
async def test_resolve_roles_to_policies_preserves_self_scope(seeded_db: AsyncSession) -> None:
    """Project scoping preserves self scope instead of widening to project."""
    policy = Policy(
        name="test:resolve:self",
        statements=[{"name": "test:resolve:self", "effect": "allow", "actions": ["user:read"], "scope": "self"}],
        is_builtin=False,
        labels={},
    )
    seeded_db.add(policy)
    await seeded_db.flush()

    role = Role(name="self-scope-role", is_builtin=False, policy_names=["test:resolve:self"], labels={})
    seeded_db.add(role)
    await seeded_db.commit()

    seen: set[str] = set()
    result: list[dict[str, object]] = []
    await _resolve_roles_to_policies(seeded_db, ["self-scope-role"], seen, result, project="my-project")

    assert len(result) >= 1
    proj_stmts = [s for s in result if s.get("project") == "my-project"]
    assert len(proj_stmts) >= 1
    assert proj_stmts[0]["scope"] == "self"


@pytest.mark.asyncio
async def test_resolve_builtin_role_preserves_self_scope(seeded_db: AsyncSession) -> None:
    """Builtin roles with self-scoped policies preserve scope in project context."""
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    await _resolve_roles_to_policies(seeded_db, ["authenticated"], seen, result, project="my-project")

    assert len(result) >= 1
    self_stmts = [s for s in result if s.get("scope") == "self" and s.get("project") == "my-project"]
    assert len(self_stmts) >= 1
    widened_stmts = [s for s in result if s.get("scope") == "project" and s.get("project") == "my-project"]
    assert len(widened_stmts) == 0


@pytest.mark.asyncio
async def test_resolve_roles_to_policies_deduplication(seeded_db: AsyncSession) -> None:
    """Duplicate policy names are deduplicated via seen set."""
    policy = Policy(
        name="test:dedup:any",
        statements=[{"name": "test:dedup:any", "effect": "allow", "actions": ["read"], "scope": "any"}],
        is_builtin=False,
        labels={},
    )
    seeded_db.add(policy)
    await seeded_db.flush()

    role1 = Role(name="dedup-role-1", is_builtin=False, policy_names=["test:dedup:any"], labels={})
    role2 = Role(name="dedup-role-2", is_builtin=False, policy_names=["test:dedup:any"], labels={})
    seeded_db.add(role1)
    seeded_db.add(role2)
    await seeded_db.commit()

    seen: set[str] = set()
    result: list[dict[str, object]] = []
    await _resolve_roles_to_policies(seeded_db, ["dedup-role-1", "dedup-role-2"], seen, result)
    # Same policy name should appear only once
    names = [s.get("name") for s in result]
    assert names.count("test:dedup:any") == 1


# ============================================================================
# resolve_effective_policies
# ============================================================================


@pytest.mark.asyncio
async def test_resolve_effective_policies_global_group_roles(seeded_db: AsyncSession, test_user: User) -> None:
    """User gets policies from group role assignments (global scope)."""
    # test_user is implicitly in authenticated group which has authenticated + user roles
    policies = await resolve_effective_policies(seeded_db, test_user.id)
    assert len(policies) > 0
    names = {p["name"] for p in policies}
    # Default role should include common policies
    assert any("read" in n for n in names)


@pytest.mark.asyncio
async def test_resolve_effective_policies_direct_user_role(seeded_db: AsyncSession, test_user: User) -> None:
    """User gets policies from direct user role assignments."""
    # Create a policy and role, then assign directly to user
    policy = Policy(
        name="direct:test:any",
        statements=[{"name": "direct:test:any", "effect": "allow", "actions": ["direct-action"], "scope": "any"}],
        is_builtin=False,
        labels={},
    )
    seeded_db.add(policy)
    await seeded_db.flush()

    role = Role(name="direct-role", is_builtin=False, policy_names=["direct:test:any"], labels={})
    seeded_db.add(role)
    await seeded_db.flush()

    assignment = RoleAssignment(principal_id=test_user.id, role_name="direct-role")
    seeded_db.add(assignment)
    await seeded_db.commit()

    policies = await resolve_effective_policies(seeded_db, test_user.id)
    names = {p["name"] for p in policies}
    assert "direct:test:any" in names


@pytest.mark.asyncio
async def test_resolve_effective_policies_project_scoped(seeded_db: AsyncSession, test_user: User) -> None:
    """User gets project-scoped policies from project role assignments."""
    project = Project(name="resolver-test-proj", labels={})
    seeded_db.add(project)
    await seeded_db.flush()

    policy = Policy(
        name="proj:test:any",
        statements=[{"name": "proj:test:any", "effect": "allow", "actions": ["proj-action"], "scope": "any"}],
        is_builtin=False,
        labels={},
    )
    seeded_db.add(policy)
    await seeded_db.flush()

    role = Role(name="proj-role", is_builtin=False, policy_names=["proj:test:any"], labels={})
    seeded_db.add(role)
    await seeded_db.flush()

    assignment = RoleAssignment(principal_id=test_user.id, role_name="proj-role", project_id=project.id)
    seeded_db.add(assignment)
    await seeded_db.commit()

    policies = await resolve_effective_policies(seeded_db, test_user.id)
    proj_policies = [p for p in policies if p.get("scope") == "project" and p.get("project") == "resolver-test-proj"]
    assert len(proj_policies) >= 1


@pytest.mark.asyncio
async def test_resolve_effective_policies_group_project_scoped(seeded_db: AsyncSession, test_user: User) -> None:
    """User gets project-scoped policies via group membership."""
    project = Project(name="group-proj-test", labels={})
    seeded_db.add(project)
    await seeded_db.flush()

    policy = Policy(
        name="grp-proj:test:any",
        statements=[{"name": "grp-proj:test:any", "effect": "allow", "actions": ["grp-proj-action"], "scope": "any"}],
        is_builtin=False,
        labels={},
    )
    seeded_db.add(policy)
    await seeded_db.flush()

    role = Role(name="grp-proj-role", is_builtin=False, policy_names=["grp-proj:test:any"], labels={})
    seeded_db.add(role)
    await seeded_db.flush()

    group = Group(id=uuid4(), name="proj-test-grp", description="", labels={})
    seeded_db.add(group)
    await seeded_db.flush()

    # Assign group to project-scoped role
    seeded_db.add(
        RoleAssignment(
            group_id=group.id,
            role_name="grp-proj-role",
            project_id=project.id,
        )
    )
    # Add user to group
    await seeded_db.exec(insert(user_groups).values(user_id=test_user.id, group_id=group.id))
    await seeded_db.commit()

    policies = await resolve_effective_policies(seeded_db, test_user.id)
    proj_policies = [p for p in policies if p.get("scope") == "project" and p.get("project") == "group-proj-test"]
    assert len(proj_policies) >= 1


@pytest.mark.asyncio
async def test_resolve_effective_policies_cross_project_isolation(seeded_db: AsyncSession, test_user: User) -> None:
    """Identically-named roles/policies in different projects resolve independently."""
    proj_a = Project(name="isolation-proj-a", labels={})
    proj_b = Project(name="isolation-proj-b", labels={})
    seeded_db.add(proj_a)
    seeded_db.add(proj_b)
    await seeded_db.flush()

    policy_a = Policy(
        name="shared-policy",
        statements=[{"name": "shared-policy", "effect": "allow", "actions": ["action-a"], "scope": "any"}],
        is_builtin=False,
        labels={},
        project_id=proj_a.id,
    )
    policy_b = Policy(
        name="shared-policy",
        statements=[{"name": "shared-policy", "effect": "allow", "actions": ["action-b"], "scope": "any"}],
        is_builtin=False,
        labels={},
        project_id=proj_b.id,
    )
    seeded_db.add(policy_a)
    seeded_db.add(policy_b)
    await seeded_db.flush()

    role_a = Role(name="shared-role", is_builtin=False, policy_names=["shared-policy"], labels={}, project_id=proj_a.id)
    role_b = Role(name="shared-role", is_builtin=False, policy_names=["shared-policy"], labels={}, project_id=proj_b.id)
    seeded_db.add(role_a)
    seeded_db.add(role_b)
    await seeded_db.flush()

    assignment = RoleAssignment(
        principal_id=test_user.id,
        role_name="shared-role",
        project_id=proj_b.id,
    )
    seeded_db.add(assignment)
    await seeded_db.commit()

    policies = await resolve_effective_policies(seeded_db, test_user.id)
    proj_b_policies = [p for p in policies if p.get("scope") == "project" and p.get("project") == "isolation-proj-b"]

    assert len(proj_b_policies) == 1
    assert proj_b_policies[0]["actions"] == ["action-b"]

    proj_a_policies = [p for p in policies if p.get("scope") == "project" and p.get("project") == "isolation-proj-a"]
    assert len(proj_a_policies) == 0


# ============================================================================
# resolve_user_groups
# ============================================================================


@pytest.mark.asyncio
async def test_resolve_user_groups_includes_authenticated(seeded_db: AsyncSession, test_user: User) -> None:
    """All users have 'authenticated' in their groups."""
    groups = await resolve_user_groups(seeded_db, test_user.id)
    group_names = {g["name"] for g in groups}
    assert "authenticated" in group_names


@pytest.mark.asyncio
async def test_resolve_user_groups_includes_explicit(seeded_db: AsyncSession, test_user: User) -> None:
    """Explicit group memberships appear in resolved groups."""
    group = Group(id=uuid4(), name="explicit-grp", description="", labels={"team": "alpha"})
    seeded_db.add(group)
    await seeded_db.flush()
    await seeded_db.exec(insert(user_groups).values(user_id=test_user.id, group_id=group.id))
    await seeded_db.commit()

    groups = await resolve_user_groups(seeded_db, test_user.id)
    match = [g for g in groups if g["name"] == "explicit-grp"]
    assert len(match) == 1
    assert match[0]["labels"] == {"team": "alpha"}


@pytest.mark.asyncio
async def test_resolve_user_groups_empty_when_no_groups(
    seeded_db: AsyncSession,
) -> None:
    """User with only authenticated group membership gets that group."""
    orphan = User(
        id=uuid4(),
        username="orphan",
        email="orphan@test.com",
        first_name="Orphan",
        password_hash="$argon2id$test",  # noqa: S106
    )
    seeded_db.add(orphan)
    await seeded_db.flush()

    # Add to authenticated group (explicit membership)
    auth_group = (await seeded_db.exec(select(Group).where(Group.name == "authenticated"))).one()
    await seeded_db.exec(insert(user_groups).values(user_id=orphan.id, group_id=auth_group.id))
    await seeded_db.commit()

    groups = await resolve_user_groups(seeded_db, orphan.id)
    group_names = {g["name"] for g in groups}
    assert "authenticated" in group_names


# ============================================================================
# resolve_effective_policies — service account
# ============================================================================


@pytest.mark.asyncio
async def test_resolve_effective_policies_service_account_direct_role(seeded_db: AsyncSession, test_user: User) -> None:
    """Service account gets policies from direct role assignment."""
    project = Project(name="sa-resolver-proj", labels={})
    seeded_db.add(project)
    await seeded_db.flush()

    sa = ServiceAccount(
        id=uuid4(),
        name=f"sa-{uuid4().hex[:8]}",
        client_id=f"nx_sa_{uuid4().hex[:16]}",
        hashed_secret="$argon2id$v=19$m=65536,t=3,p=4$test",  # noqa: S106
        project_id=project.id,
        created_by=test_user.id,
    )
    seeded_db.add(sa)
    await seeded_db.flush()

    policy = Policy(
        name="sa:direct:any",
        statements=[{"name": "sa:direct:any", "effect": "allow", "actions": ["sa-action"], "scope": "any"}],
        is_builtin=False,
        labels={},
    )
    seeded_db.add(policy)
    await seeded_db.flush()

    role = Role(name="sa-direct-role", is_builtin=False, policy_names=["sa:direct:any"], labels={})
    seeded_db.add(role)
    await seeded_db.flush()

    assignment = RoleAssignment(
        principal_id=sa.id,
        role_name="sa-direct-role",
        project_id=project.id,
    )
    seeded_db.add(assignment)
    await seeded_db.commit()

    policies = await resolve_effective_policies(seeded_db, sa.id)
    names = {p["name"] for p in policies}
    assert "sa:direct:any" in names
    proj_policies = [p for p in policies if p.get("project") == "sa-resolver-proj"]
    assert len(proj_policies) >= 1
