"""Unit tests for RoleAssignmentService.

Tests cover:
- Assign: user/group/service_account, global/project-scoped, duplicate rejection, validation
- Get: existing and non-existent assignments
- List: filters, visibility restrictions, include_total, default sort
- Revoke: existing and non-existent assignments
- Visibility: admin, own user/group/service_account, project-admin, cross-project
"""

from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models.project import Project
from syntara.authz.models.role import Role
from syntara.authz.seed import seed_authz_data
from syntara.authz.services.role_assignment_service import RoleAssignmentService
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.models.group import Group
from syntara.service_accounts.models.service_account import ServiceAccount


@pytest.fixture
async def seeded_db(test_db_session: AsyncSession) -> AsyncSession:
    """Seed authz data and return the session."""
    await seed_authz_data(test_db_session)
    return test_db_session


async def _create_project(session: AsyncSession, name: str = "test-project") -> Project:
    """Create a project for testing."""
    project = Project(id=uuid4(), name=name, description=f"Project {name}", labels={})
    session.add(project)
    await session.flush()
    return project


async def _create_group(session: AsyncSession, name: str = "test-svc-group") -> Group:
    """Create a group for testing."""
    group = Group(id=uuid4(), name=name, description=f"Group {name}", labels={})
    session.add(group)
    await session.flush()
    return group


# ============================================================================
# Assign
# ============================================================================


@pytest.mark.asyncio
async def test_assign_user_role_global(seeded_db: AsyncSession, test_user: User) -> None:
    """Assign a system role to a user without project scope."""
    svc = RoleAssignmentService(seeded_db, test_user)
    result = await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    assert result["principal_id"] == test_user.id
    assert result["role_name"] == "admin"
    assert result["project_id"] is None
    assert result["principal_name"] == test_user.username
    assert "role_description" in result
    assert "role_policies" in result


@pytest.mark.asyncio
async def test_assign_group_role_global(seeded_db: AsyncSession, test_user: User) -> None:
    """Assign a system role to a group without project scope."""
    group = await _create_group(seeded_db)
    svc = RoleAssignmentService(seeded_db, test_user)
    result = await svc.assign(
        group_id=group.id,
        role_name="user",
    )
    assert result["principal_id"] is None
    assert result["group_id"] == group.id
    assert result["role_name"] == "user"
    assert result["project_id"] is None
    assert result["principal_name"] == group.name


@pytest.mark.asyncio
async def test_assign_user_role_project_scoped(seeded_db: AsyncSession, test_user: User) -> None:
    """Assign a project role to a user with project scope."""
    project = await _create_project(seeded_db)
    svc = RoleAssignmentService(seeded_db, test_user)
    result = await svc.assign(
        principal_id=test_user.id,
        role_name="project-user",
        project_id=project.id,
    )
    assert result["role_name"] == "project-user"
    assert result["project_id"] == project.id
    assert result["project_name"] == project.name


@pytest.mark.asyncio
async def test_assign_group_role_project_scoped(seeded_db: AsyncSession, test_user: User) -> None:
    """Assign a project role to a group with project scope."""
    project = await _create_project(seeded_db)
    group = await _create_group(seeded_db)
    svc = RoleAssignmentService(seeded_db, test_user)
    result = await svc.assign(
        group_id=group.id,
        role_name="project-user",
        project_id=project.id,
    )
    assert result["role_name"] == "project-user"
    assert result["project_id"] == project.id
    assert result["principal_name"] == group.name


@pytest.mark.asyncio
async def test_assign_duplicate_rejected(seeded_db: AsyncSession, test_user: User) -> None:
    """Duplicate assignment raises SafeValueError."""
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="auditor",
    )
    with pytest.raises(SafeValueError, match="already assigned"):
        await svc.assign(
            principal_id=test_user.id,
            role_name="auditor",
        )


@pytest.mark.asyncio
async def test_assign_nonexistent_user(seeded_db: AsyncSession, test_user: User) -> None:
    """Assigning to a nonexistent user raises SafeValueError."""
    svc = RoleAssignmentService(seeded_db, test_user)
    nonexistent_id = uuid4()
    with pytest.raises(SafeValueError, match=r"Principal .* not found"):
        await svc.assign(
            principal_id=nonexistent_id,
            role_name="admin",
        )


@pytest.mark.asyncio
async def test_assign_nonexistent_role(seeded_db: AsyncSession, test_user: User) -> None:
    """Assigning an unknown role raises SafeValueError."""
    svc = RoleAssignmentService(seeded_db, test_user)
    with pytest.raises(SafeValueError, match="not found"):
        await svc.assign(
            principal_id=test_user.id,
            role_name="nonexistent-role",
        )


@pytest.mark.asyncio
async def test_assign_system_role_with_project_rejected(seeded_db: AsyncSession, test_user: User) -> None:
    """System role cannot be assigned with a project_id."""
    project = await _create_project(seeded_db)
    svc = RoleAssignmentService(seeded_db, test_user)
    with pytest.raises(SafeValueError, match="system role"):
        await svc.assign(
            principal_id=test_user.id,
            role_name="admin",
            project_id=project.id,
        )


@pytest.mark.asyncio
async def test_assign_project_role_without_project_rejected(seeded_db: AsyncSession, test_user: User) -> None:
    """Project role requires a project_id."""
    svc = RoleAssignmentService(seeded_db, test_user)
    with pytest.raises(SafeValueError, match="requires a project_id"):
        await svc.assign(
            principal_id=test_user.id,
            role_name="project-user",
        )


# ============================================================================
# Get
# ============================================================================


@pytest.mark.asyncio
async def test_get_existing_assignment(seeded_db: AsyncSession, test_user: User) -> None:
    """Get an existing assignment with resolved names and role info."""
    svc = RoleAssignmentService(seeded_db, test_user)
    created = await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    fetched = await svc.get(created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["principal_name"] == test_user.username
    assert fetched["role_name"] == "admin"
    assert "role_description" in fetched
    assert "role_policies" in fetched
    assert isinstance(fetched["role_policies"], list)
    assert len(fetched["role_policies"]) > 0


@pytest.mark.asyncio
async def test_get_nonexistent_assignment(seeded_db: AsyncSession, test_user: User) -> None:
    """Getting a nonexistent assignment raises SafeValueError."""
    svc = RoleAssignmentService(seeded_db, test_user)
    nonexistent_id = uuid4()
    with pytest.raises(SafeValueError, match="not found"):
        await svc.get(nonexistent_id)


# ============================================================================
# List
# ============================================================================


@pytest.mark.asyncio
async def test_list_all_no_filters(seeded_db: AsyncSession, test_user: User) -> None:
    """List all assignments returns both user and group types."""
    group = await _create_group(seeded_db, name="list-group")
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    await svc.assign(
        group_id=group.id,
        role_name="user",
    )
    result = await svc.list()
    resources = result["resources"]
    # Seeded assignments exist too, so we should have at least our 2 plus seeded ones
    assert len(resources) >= 2


@pytest.mark.asyncio
async def test_list_filter_by_role_name(seeded_db: AsyncSession, test_user: User) -> None:
    """Filter by role_name returns only matching assignments."""
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="auditor",
    )
    result = await svc.list(role_name="auditor")
    assert len(result["resources"]) >= 1
    for r in result["resources"]:
        assert r["role_name"] == "auditor"


@pytest.mark.asyncio
async def test_list_filter_by_project_id(seeded_db: AsyncSession, test_user: User) -> None:
    """Filter by project_id returns only project-scoped assignments."""
    project = await _create_project(seeded_db, name="filter-project")
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="project-admin",
        project_id=project.id,
    )
    result = await svc.list(project_id=project.id)
    assert len(result["resources"]) >= 1
    for r in result["resources"]:
        assert r["project_id"] == project.id


@pytest.mark.asyncio
async def test_list_restrict_user_id_sees_own(seeded_db: AsyncSession, test_user: User) -> None:
    """Restricting by user_id returns only that user's assignments."""
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    result = await svc.list(restrict_user_id=test_user.id)
    for r in result["resources"]:
        assert r["principal_id"] == test_user.id


@pytest.mark.asyncio
async def test_list_restrict_group_ids_sees_own(seeded_db: AsyncSession, test_user: User) -> None:
    """Restricting by group_ids returns that group's assignments."""
    group = await _create_group(seeded_db, name="restrict-group")
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        group_id=group.id,
        role_name="user",
    )
    # Restrict to just this group; no user visibility
    result = await svc.list(restrict_user_id=uuid4(), restrict_group_ids=[group.id])
    group_resources = [r for r in result["resources"] if r["group_id"] is not None]
    assert len(group_resources) >= 1
    for r in group_resources:
        assert r["group_id"] == group.id


@pytest.mark.asyncio
async def test_list_include_total(seeded_db: AsyncSession, test_user: User) -> None:
    """Setting include_total returns a count of matching assignments."""
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    result = await svc.list(include_total=True)
    assert result["total"] is not None
    assert result["total"] >= 1
    assert result["total"] == len(result["resources"])


@pytest.mark.asyncio
async def test_list_default_sort_created_at_desc(seeded_db: AsyncSession, test_user: User) -> None:
    """Default sort order is created_at descending."""
    group = await _create_group(seeded_db, name="sort-group")
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    await svc.assign(
        group_id=group.id,
        role_name="user",
    )
    result = await svc.list()
    resources = result["resources"]
    if len(resources) >= 2:
        created_ats = [r["created_at"] for r in resources]
        assert created_ats == sorted(created_ats, reverse=True)


# ============================================================================
# Revoke
# ============================================================================


@pytest.mark.asyncio
async def test_revoke_existing_assignment(seeded_db: AsyncSession, test_user: User) -> None:
    """Revoking an existing assignment removes it from the database."""
    svc = RoleAssignmentService(seeded_db, test_user)
    created = await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    await svc.revoke(created["id"])
    with pytest.raises(SafeValueError, match="not found"):
        await svc.get(created["id"])


@pytest.mark.asyncio
async def test_revoke_nonexistent_assignment(seeded_db: AsyncSession, test_user: User) -> None:
    """Revoking a nonexistent assignment raises SafeValueError."""
    svc = RoleAssignmentService(seeded_db, test_user)
    nonexistent_id = uuid4()
    with pytest.raises(SafeValueError, match="not found"):
        await svc.revoke(nonexistent_id)


# ============================================================================
# Visibility
# ============================================================================


@pytest.mark.asyncio
async def test_is_visible_admin_sees_everything(seeded_db: AsyncSession, test_user: User) -> None:
    """Admin with all_projects=True can see any assignment."""
    svc = RoleAssignmentService(seeded_db, test_user)
    assignment = {
        "principal_id": uuid4(),
        "project_id": uuid4(),
    }
    assert svc.is_visible(
        assignment,
        all_projects=True,
        user_id=test_user.id,
        group_ids=[],
        allowed_project_ids=[],
    )


@pytest.mark.asyncio
async def test_is_visible_own_user_assignment(seeded_db: AsyncSession, test_user: User) -> None:
    """User can see their own user-type assignment."""
    svc = RoleAssignmentService(seeded_db, test_user)
    assignment = {
        "principal_id": test_user.id,
        "project_id": None,
    }
    assert svc.is_visible(
        assignment,
        all_projects=False,
        user_id=test_user.id,
        group_ids=[],
        allowed_project_ids=[],
    )


@pytest.mark.asyncio
async def test_is_visible_own_group_assignment(seeded_db: AsyncSession, test_user: User) -> None:
    """User can see assignments for groups they belong to."""
    group_id = uuid4()
    svc = RoleAssignmentService(seeded_db, test_user)
    assignment = {
        "principal_id": None,
        "group_id": group_id,
        "project_id": None,
    }
    assert svc.is_visible(
        assignment,
        all_projects=False,
        user_id=test_user.id,
        group_ids=[group_id],
        allowed_project_ids=[],
    )


@pytest.mark.asyncio
async def test_is_visible_project_admin_via_allowed_projects(seeded_db: AsyncSession, test_user: User) -> None:
    """Project admin can see assignments in their allowed projects."""
    project_id = uuid4()
    svc = RoleAssignmentService(seeded_db, test_user)
    assignment = {
        "principal_id": uuid4(),
        "project_id": project_id,
    }
    assert svc.is_visible(
        assignment,
        all_projects=False,
        user_id=test_user.id,
        group_ids=[],
        allowed_project_ids=[project_id],
    )


@pytest.mark.asyncio
async def test_is_visible_cross_project_not_visible(seeded_db: AsyncSession, test_user: User) -> None:
    """Assignment in a different project is not visible."""
    svc = RoleAssignmentService(seeded_db, test_user)
    assignment = {
        "principal_id": uuid4(),
        "project_id": uuid4(),
    }
    assert not svc.is_visible(
        assignment,
        all_projects=False,
        user_id=test_user.id,
        group_ids=[],
        allowed_project_ids=[uuid4()],
    )


# ============================================================================
# List — filter coverage
# ============================================================================


@pytest.mark.asyncio
async def test_list_filter_by_principal_id(seeded_db: AsyncSession, test_user: User) -> None:
    """Filter by principal_id returns only that principal's assignments."""
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    result = await svc.list(principal_id=test_user.id)
    assert len(result["resources"]) >= 1
    for r in result["resources"]:
        assert r["principal_id"] == test_user.id


@pytest.mark.asyncio
async def test_list_filter_by_group_id(seeded_db: AsyncSession, test_user: User) -> None:
    """Filter by group_id returns only that group's assignments."""
    group = await _create_group(seeded_db, "filter-group")
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(group_id=group.id, role_name="user")
    result = await svc.list(group_id=group.id)
    assert len(result["resources"]) >= 1
    for r in result["resources"]:
        assert r["group_id"] == group.id


@pytest.mark.asyncio
async def test_list_filter_by_principal_name(seeded_db: AsyncSession, test_user: User) -> None:
    """Filter by principal_name returns only matching assignments."""
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    result = await svc.list(principal_name=test_user.username)
    assert len(result["resources"]) >= 1
    for r in result["resources"]:
        assert r["principal_name"] == test_user.username


@pytest.mark.asyncio
async def test_list_filter_by_principal_name_contains(seeded_db: AsyncSession, test_user: User) -> None:
    """Filter by principal_name_contains returns partial matches."""
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    partial = test_user.username[:3]
    result = await svc.list(principal_name_contains=partial)
    assert len(result["resources"]) >= 1
    for r in result["resources"]:
        assert partial.lower() in r["principal_name"].lower()


@pytest.mark.asyncio
async def test_list_filter_by_role_name_contains(seeded_db: AsyncSession, test_user: User) -> None:
    """Filter by role_name_contains returns partial matches."""
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="auditor",
    )
    result = await svc.list(role_name_contains="aud")
    assert len(result["resources"]) >= 1
    for r in result["resources"]:
        assert "aud" in r["role_name"].lower()


# ============================================================================
# List — sort coverage
# ============================================================================


@pytest.mark.asyncio
async def test_list_sort_by_role_name_ascending(seeded_db: AsyncSession, test_user: User) -> None:
    """Sort by role_name ascending."""
    group = await _create_group(seeded_db, name="sort-asc-group")
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    await svc.assign(
        group_id=group.id,
        role_name="user",
    )
    result = await svc.list(sort="role_name")
    resources = result["resources"]
    role_names = [r["role_name"] for r in resources]
    assert role_names == sorted(role_names)


@pytest.mark.asyncio
async def test_list_sort_by_principal_name(seeded_db: AsyncSession, test_user: User) -> None:
    """Sort by principal_name descending."""
    group = await _create_group(seeded_db, name="aaa-group")
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    await svc.assign(
        group_id=group.id,
        role_name="user",
    )
    result = await svc.list(sort="-principal_name")
    resources = result["resources"]
    names = [r["principal_name"] for r in resources]
    assert names == sorted(names, reverse=True)


@pytest.mark.asyncio
async def test_list_sort_by_project_name(seeded_db: AsyncSession, test_user: User) -> None:
    """Sort by project_name ascending."""
    project_a = await _create_project(seeded_db, name="alpha-project")
    project_z = await _create_project(seeded_db, name="zeta-project")
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="project-admin",
        project_id=project_z.id,
    )
    await svc.assign(
        principal_id=test_user.id,
        role_name="project-admin",
        project_id=project_a.id,
    )
    result = await svc.list(sort="project_name")
    resources = result["resources"]
    project_names = [r["project_name"] for r in resources if r["project_name"] is not None]
    assert len(project_names) >= 2


@pytest.mark.asyncio
async def test_list_invalid_sort_field_defaults(seeded_db: AsyncSession, test_user: User) -> None:
    """Invalid sort field falls back to created_at descending."""
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    result = await svc.list(sort="nonexistent_field")
    assert len(result["resources"]) >= 1


# ============================================================================
# List — pagination coverage
# ============================================================================


@pytest.mark.asyncio
async def test_list_pagination_forward_and_backward(seeded_db: AsyncSession, test_user: User) -> None:
    """Paginate forward then backward to cover cursor logic."""
    svc = RoleAssignmentService(seeded_db, test_user)
    for i in range(3):
        group = await _create_group(seeded_db, name=f"page-group-{i}")
        await svc.assign(
            group_id=group.id,
            role_name="user",
        )
    await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )

    page1 = await svc.list(limit=2)
    assert len(page1["resources"]) == 2
    assert page1["next"] is not None

    page2 = await svc.list(limit=2, cursor=page1["next"])
    assert len(page2["resources"]) >= 1
    assert page2["prev"] is not None

    page1_again = await svc.list(limit=2, cursor=page2["prev"])
    assert len(page1_again["resources"]) >= 1


# ============================================================================
# List — visibility with allowed_project_ids
# ============================================================================


@pytest.mark.asyncio
async def test_list_restrict_allowed_project_ids(seeded_db: AsyncSession, test_user: User) -> None:
    """Restricting by allowed_project_ids returns only those project assignments."""
    project = await _create_project(seeded_db, name="allowed-project")
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="project-admin",
        project_id=project.id,
    )
    result = await svc.list(
        restrict_user_id=uuid4(),
        allowed_project_ids=[project.id],
    )
    for r in result["resources"]:
        assert r["project_id"] == project.id


# ============================================================================
# Revoke — with project_id validation
# ============================================================================


@pytest.mark.asyncio
async def test_revoke_with_project_id_validation(seeded_db: AsyncSession, test_user: User) -> None:
    """Revoking with project_id only deletes if assignment matches that project."""
    project = await _create_project(seeded_db, name="revoke-project")
    svc = RoleAssignmentService(seeded_db, test_user)
    created = await svc.assign(
        principal_id=test_user.id,
        role_name="project-admin",
        project_id=project.id,
    )
    wrong_project_id = uuid4()
    with pytest.raises(SafeValueError, match="not found"):
        await svc.revoke(created["id"], project_id=wrong_project_id)
    await svc.revoke(created["id"], project_id=project.id)
    with pytest.raises(SafeValueError, match="not found"):
        await svc.get(created["id"])


# ============================================================================
# Validation — nonexistent group
# ============================================================================


@pytest.mark.asyncio
async def test_assign_nonexistent_group(seeded_db: AsyncSession, test_user: User) -> None:
    """Assigning to a nonexistent group raises SafeValueError."""
    svc = RoleAssignmentService(seeded_db, test_user)
    nonexistent_id = uuid4()
    with pytest.raises(SafeValueError, match=r"Group .* not found"):
        await svc.assign(
            group_id=nonexistent_id,
            role_name="user",
        )


# ============================================================================
# Custom roles
# ============================================================================


async def _create_custom_role(
    session: AsyncSession,
    name: str = "custom-role",
    scope: str = "system",
    project_id: UUID | None = None,
) -> Role:
    """Create a custom (non-builtin) role for testing."""
    role = Role(
        id=uuid4(),
        name=name,
        description=f"Custom role {name}",
        is_builtin=False,
        scope=scope,
        project_id=project_id,
        policy_names=["some-policy"],
    )
    session.add(role)
    await session.flush()
    return role


@pytest.mark.asyncio
async def test_assign_custom_system_role(seeded_db: AsyncSession, test_user: User) -> None:
    """Assign a custom system role and verify enrichment resolves from DB."""
    role = await _create_custom_role(seeded_db, name="custom-sys")
    svc = RoleAssignmentService(seeded_db, test_user)
    result = await svc.assign(
        principal_id=test_user.id,
        role_name=role.name,
    )
    assert result["role_name"] == "custom-sys"
    assert result["role_description"] == role.description
    assert result["role_policies"] == ["some-policy"]


@pytest.mark.asyncio
async def test_assign_custom_project_role(seeded_db: AsyncSession, test_user: User) -> None:
    """Assign a custom project-scoped role."""
    project = await _create_project(seeded_db, name="custom-role-project")
    role = await _create_custom_role(seeded_db, name="custom-proj", scope="project", project_id=project.id)
    svc = RoleAssignmentService(seeded_db, test_user)
    result = await svc.assign(
        principal_id=test_user.id,
        role_name=role.name,
        project_id=project.id,
    )
    assert result["role_name"] == "custom-proj"
    assert result["project_id"] == project.id


@pytest.mark.asyncio
async def test_assign_custom_system_role_with_project_rejected(seeded_db: AsyncSession, test_user: User) -> None:
    """Custom system role cannot be assigned with a project_id."""
    project = await _create_project(seeded_db, name="reject-project")
    await _create_custom_role(seeded_db, name="custom-sys-only", scope="system")
    svc = RoleAssignmentService(seeded_db, test_user)
    with pytest.raises(SafeValueError, match="system role"):
        await svc.assign(
            principal_id=test_user.id,
            role_name="custom-sys-only",
            project_id=project.id,
        )


# ============================================================================
# Sort by principal_name + cursor round-trip
# ============================================================================


@pytest.mark.asyncio
async def test_list_sort_by_principal_name_global_order(seeded_db: AsyncSession, test_user: User) -> None:
    """Paginating with sort=principal_name produces globally consistent order."""
    group = await _create_group(seeded_db, name="alpha-group")
    svc = RoleAssignmentService(seeded_db, test_user)

    for name in ["role-a", "role-b", "role-c"]:
        await _create_custom_role(seeded_db, name=name, scope="system")

    await svc.assign(
        principal_id=test_user.id,
        role_name="role-a",
    )
    await svc.assign(
        principal_id=test_user.id,
        role_name="role-b",
    )
    await svc.assign(
        group_id=group.id,
        role_name="role-c",
    )

    all_names: list[str] = []
    cursor = None
    while True:
        result = await svc.list(limit=2, cursor=cursor, sort="principal_name")
        all_names.extend(r["principal_name"] for r in result["resources"])
        if not result["next"]:
            break
        cursor = result["next"]

    assert all_names == sorted(all_names), f"Global sort broken: {all_names}"
    assert len(all_names) == len(set(all_names)) or len(all_names) >= 3


# ============================================================================
# Service account support
# ============================================================================


async def _create_service_account(
    session: AsyncSession,
    project: Project,
    created_by: UUID,
    name: str | None = None,
) -> ServiceAccount:
    """Create a service account for testing."""
    sa = ServiceAccount(
        id=uuid4(),
        name=name or f"sa-{uuid4().hex[:8]}",
        client_id=f"nx_sa_{uuid4().hex[:16]}",
        hashed_secret="$argon2id$v=19$m=65536,t=3,p=4$test",  # noqa: S106
        project_id=project.id,
        created_by=created_by,
    )
    session.add(sa)
    await session.flush()
    return sa


@pytest.mark.asyncio
async def test_assign_service_account_role_project_scoped(seeded_db: AsyncSession, test_user: User) -> None:
    """Assign a project role to a service account."""
    project = await _create_project(seeded_db, name="sa-project")
    sa = await _create_service_account(seeded_db, project, created_by=test_user.id)
    svc = RoleAssignmentService(seeded_db, test_user)
    result = await svc.assign(
        principal_id=sa.id,
        role_name="project-user",
        project_id=project.id,
    )
    assert result["principal_id"] == sa.id
    assert result["role_name"] == "project-user"
    assert result["project_id"] == project.id
    assert result["principal_name"] == sa.name


@pytest.mark.asyncio
async def test_assign_nonexistent_service_account(seeded_db: AsyncSession, test_user: User) -> None:
    """Assigning to a nonexistent service account raises SafeValueError."""
    svc = RoleAssignmentService(seeded_db, test_user)
    nonexistent_id = uuid4()
    with pytest.raises(SafeValueError, match=r"Principal .* not found"):
        await svc.assign(
            principal_id=nonexistent_id,
            role_name="user",
        )


@pytest.mark.asyncio
async def test_get_service_account_assignment(seeded_db: AsyncSession, test_user: User) -> None:
    """Get resolves service account principal_name via _query_one."""
    project = await _create_project(seeded_db, name="sa-get-project")
    sa = await _create_service_account(seeded_db, project, created_by=test_user.id, name="my-sa")
    svc = RoleAssignmentService(seeded_db, test_user)
    created = await svc.assign(
        principal_id=sa.id,
        role_name="project-user",
        project_id=project.id,
    )
    fetched = await svc.get(created["id"])
    assert fetched["principal_name"] == "my-sa"


@pytest.mark.asyncio
async def test_list_includes_service_account_assignments(seeded_db: AsyncSession, test_user: User) -> None:
    """List returns service account assignments with resolved principal_name."""
    project = await _create_project(seeded_db, name="sa-list-project")
    sa = await _create_service_account(seeded_db, project, created_by=test_user.id, name="list-sa")
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=sa.id,
        role_name="project-user",
        project_id=project.id,
    )
    result = await svc.list()
    assert len(result["resources"]) >= 1
    sa_resources = [r for r in result["resources"] if r["principal_id"] == sa.id]
    assert len(sa_resources) == 1
    assert sa_resources[0]["principal_name"] == "list-sa"


@pytest.mark.asyncio
async def test_list_restrict_user_id_sees_own_service_account(seeded_db: AsyncSession, test_user: User) -> None:
    """Restricting by restrict_user_id returns SA assignments when principal_id matches."""
    project = await _create_project(seeded_db, name="sa-visibility-project")
    sa = await _create_service_account(seeded_db, project, created_by=test_user.id)
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=sa.id,
        role_name="project-user",
        project_id=project.id,
    )
    result = await svc.list(restrict_user_id=sa.id)
    sa_resources = [r for r in result["resources"] if r["principal_id"] == sa.id]
    assert len(sa_resources) >= 1


@pytest.mark.asyncio
async def test_is_visible_own_service_account_assignment(seeded_db: AsyncSession, test_user: User) -> None:
    """Service account can see its own assignment via is_visible."""
    sa_id = uuid4()
    svc = RoleAssignmentService(seeded_db, test_user)
    assignment = {
        "principal_id": sa_id,
        "project_id": None,
    }
    assert svc.is_visible(
        assignment,
        all_projects=False,
        user_id=sa_id,
        group_ids=[],
        allowed_project_ids=[],
    )


# ============================================================================
# principal_type regression coverage
# ============================================================================


async def test_assign_user_returns_principal_type_user(seeded_db: AsyncSession, test_user: User) -> None:
    """User assignment returns principal_type='user'."""
    svc = RoleAssignmentService(seeded_db, test_user)
    result = await svc.assign(principal_id=test_user.id, role_name="admin")
    assert result["principal_type"] == "user"


@pytest.mark.asyncio
async def test_assign_group_returns_principal_type_group(seeded_db: AsyncSession, test_user: User) -> None:
    """Group assignment returns principal_type='group'."""
    group = await _create_group(seeded_db, name="pt-group")
    svc = RoleAssignmentService(seeded_db, test_user)
    result = await svc.assign(group_id=group.id, role_name="user")
    assert result["principal_type"] == "group"


@pytest.mark.asyncio
async def test_assign_service_account_returns_principal_type_service_account(
    seeded_db: AsyncSession, test_user: User
) -> None:
    """Service account assignment returns principal_type='service_account'."""
    project = await _create_project(seeded_db, name="pt-sa-project")
    sa = await _create_service_account(seeded_db, project, created_by=test_user.id, name="pt-sa")
    svc = RoleAssignmentService(seeded_db, test_user)
    result = await svc.assign(principal_id=sa.id, role_name="project-user", project_id=project.id)
    assert result["principal_type"] == "service_account"


@pytest.mark.asyncio
async def test_get_returns_principal_type(seeded_db: AsyncSession, test_user: User) -> None:
    """GET resolves principal_type via the joined query."""
    svc = RoleAssignmentService(seeded_db, test_user)
    created = await svc.assign(principal_id=test_user.id, role_name="auditor")
    fetched = await svc.get(created["id"])
    assert fetched["principal_type"] == "user"


@pytest.mark.asyncio
async def test_list_returns_principal_type_for_all_types(seeded_db: AsyncSession, test_user: User) -> None:
    """List returns correct principal_type for user, group, and service account."""
    group = await _create_group(seeded_db, name="pt-list-group")
    project = await _create_project(seeded_db, name="pt-list-project")
    sa = await _create_service_account(seeded_db, project, created_by=test_user.id, name="pt-list-sa")
    svc = RoleAssignmentService(seeded_db, test_user)

    await svc.assign(principal_id=test_user.id, role_name="admin")
    await svc.assign(group_id=group.id, role_name="user")
    await svc.assign(principal_id=sa.id, role_name="project-user", project_id=project.id)

    result = await svc.list()
    types_by_name = {r["principal_name"]: r["principal_type"] for r in result["resources"]}
    assert types_by_name[test_user.username] == "user"
    assert types_by_name[group.name] == "group"
    assert types_by_name["pt-list-sa"] == "service_account"


# ============================================================================
# List — sort by scope
# ============================================================================


async def test_list_sort_by_scope(seeded_db: AsyncSession, test_user: User) -> None:
    """Sort by scope returns project and system assignments in consistent order."""
    project = await _create_project(seeded_db, name="scope-sort-project")
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    await svc.assign(
        principal_id=test_user.id,
        role_name="project-admin",
        project_id=project.id,
    )
    result = await svc.list(sort="scope")
    resources = result["resources"]
    assert len(resources) >= 2
    scopes = ["project" if r["project_id"] else "system" for r in resources]
    assert scopes == sorted(scopes)


@pytest.mark.asyncio
async def test_list_sort_by_scope_descending(seeded_db: AsyncSession, test_user: User) -> None:
    """Sort by -scope returns system before project."""
    project = await _create_project(seeded_db, name="scope-desc-project")
    svc = RoleAssignmentService(seeded_db, test_user)
    await svc.assign(
        principal_id=test_user.id,
        role_name="admin",
    )
    await svc.assign(
        principal_id=test_user.id,
        role_name="project-admin",
        project_id=project.id,
    )
    result = await svc.list(sort="-scope")
    resources = result["resources"]
    assert len(resources) >= 2
    scopes = ["project" if r["project_id"] else "system" for r in resources]
    assert scopes == sorted(scopes, reverse=True)


# ============================================================================
# List — cursor pagination with sort column containing NULLs
# ============================================================================


@pytest.mark.asyncio
async def test_list_pagination_with_null_sort_values(seeded_db: AsyncSession, test_user: User) -> None:
    """Paginating with sort=project_name handles NULL project_name rows correctly.

    Rows with NULL project_name (system-scoped assignments) must not
    disappear when paginating past page 1 with NULLS LAST ordering.
    """
    project = await _create_project(seeded_db, name="null-page-project")
    svc = RoleAssignmentService(seeded_db, test_user)

    await svc.assign(
        principal_id=test_user.id,
        role_name="project-admin",
        project_id=project.id,
    )
    for i in range(3):
        group = await _create_group(seeded_db, name=f"null-page-group-{i}")
        await svc.assign(
            group_id=group.id,
            role_name="user",
        )

    all_ids: list[str] = []
    cursor = None
    while True:
        result = await svc.list(limit=2, cursor=cursor, sort="project_name")
        all_ids.extend(r["id"] for r in result["resources"])
        if not result["next"]:
            break
        cursor = result["next"]

    assert len(all_ids) >= 4, f"Expected all rows including NULLs, got {len(all_ids)}"
    assert len(all_ids) == len(set(all_ids)), "Duplicate rows in pagination"


@pytest.mark.asyncio
async def test_list_pagination_backward_with_null_sort_values(seeded_db: AsyncSession, test_user: User) -> None:
    """Backward pagination with NULL sort values returns correct results.

    Creates enough data to guarantee at least 3 pages so that going
    backward from page 3 reliably returns page 2 results.
    """
    project = await _create_project(seeded_db, name="null-back-project")
    svc = RoleAssignmentService(seeded_db, test_user)

    await svc.assign(
        principal_id=test_user.id,
        role_name="project-admin",
        project_id=project.id,
    )
    for i in range(4):
        group = await _create_group(seeded_db, name=f"null-back-group-{i}")
        await svc.assign(
            group_id=group.id,
            role_name="user",
        )

    all_ids: list[str] = []
    cursors: list[str] = []
    cursor = None
    while True:
        page = await svc.list(limit=2, cursor=cursor, sort="project_name")
        all_ids.extend(r["id"] for r in page["resources"])
        if not page["next"]:
            break
        cursors.append(page["next"])
        cursor = page["next"]

    assert len(cursors) >= 2, f"Need at least 3 pages, got {len(cursors) + 1}"

    forward_pages: list[list[str]] = []
    page_ids: list[str] = []
    cursor2 = None
    while True:
        page = await svc.list(limit=2, cursor=cursor2, sort="project_name")
        page_ids = [r["id"] for r in page["resources"]]
        forward_pages.append(page_ids)
        if not page["next"]:
            break
        cursor2 = page["next"]

    last_page = await svc.list(limit=2, cursor=cursors[-1], sort="project_name")
    assert last_page["prev"] is not None
    back = await svc.list(limit=2, cursor=last_page["prev"], sort="project_name")
    back_ids = {r["id"] for r in back["resources"]}
    expected_ids = set(forward_pages[-2])
    assert back_ids == expected_ids, f"Backward navigation returned wrong rows: {back_ids!r}, expected {expected_ids!r}"


@pytest.mark.asyncio
async def test_list_pagination_desc_forward_includes_nulls(seeded_db: AsyncSession, test_user: User) -> None:
    """DESC forward pagination includes NULL rows (NULLS LAST).

    With sort=-project_name, system assignments (NULL project_name) come
    after all project-scoped assignments. Paginating forward must not
    silently exclude them.
    """
    project = await _create_project(seeded_db, name="desc-null-project")
    svc = RoleAssignmentService(seeded_db, test_user)

    await svc.assign(
        principal_id=test_user.id,
        role_name="project-admin",
        project_id=project.id,
    )
    for i in range(3):
        group = await _create_group(seeded_db, name=f"desc-null-group-{i}")
        await svc.assign(
            group_id=group.id,
            role_name="user",
        )

    all_ids: list[str] = []
    cursor = None
    while True:
        result = await svc.list(limit=2, cursor=cursor, sort="-project_name")
        all_ids.extend(r["id"] for r in result["resources"])
        if not result["next"]:
            break
        cursor = result["next"]

    assert len(all_ids) >= 4, f"Expected all rows including NULLs, got {len(all_ids)}"
    assert len(all_ids) == len(set(all_ids)), "Duplicate rows in DESC pagination"


# ============================================================================
# List — sort by principal_type
# ============================================================================


@pytest.mark.asyncio
async def test_list_sort_by_principal_type(seeded_db: AsyncSession, test_user: User) -> None:
    """Sort by principal_type returns assignments in alphabetical order of type."""
    group = await _create_group(seeded_db, name="pt-sort-group")
    project = await _create_project(seeded_db, name="pt-sort-project")
    sa = await _create_service_account(seeded_db, project, created_by=test_user.id, name="pt-sort-sa")
    svc = RoleAssignmentService(seeded_db, test_user)

    await svc.assign(principal_id=test_user.id, role_name="admin")
    await svc.assign(group_id=group.id, role_name="user")
    await svc.assign(principal_id=sa.id, role_name="project-user", project_id=project.id)

    result = await svc.list(sort="principal_type")
    types = [r["principal_type"] for r in result["resources"]]
    assert types == sorted(types)


@pytest.mark.asyncio
async def test_list_sort_by_principal_type_descending(seeded_db: AsyncSession, test_user: User) -> None:
    """Sort by -principal_type returns assignments in reverse alphabetical order."""
    group = await _create_group(seeded_db, name="pt-sort-desc-group")
    project = await _create_project(seeded_db, name="pt-sort-desc-project")
    sa = await _create_service_account(seeded_db, project, created_by=test_user.id, name="pt-sort-desc-sa")
    svc = RoleAssignmentService(seeded_db, test_user)

    await svc.assign(principal_id=test_user.id, role_name="admin")
    await svc.assign(group_id=group.id, role_name="user")
    await svc.assign(principal_id=sa.id, role_name="project-user", project_id=project.id)

    result = await svc.list(sort="-principal_type")
    types = [r["principal_type"] for r in result["resources"]]
    assert types == sorted(types, reverse=True)


# ============================================================================
# List — filter by principal_type
# ============================================================================


@pytest.mark.asyncio
async def test_list_filter_by_principal_type_user(seeded_db: AsyncSession, test_user: User) -> None:
    """Filter by principal_type=user returns only user assignments."""
    group = await _create_group(seeded_db, name="pt-filter-group")
    svc = RoleAssignmentService(seeded_db, test_user)

    await svc.assign(principal_id=test_user.id, role_name="admin")
    await svc.assign(group_id=group.id, role_name="user")

    result = await svc.list(principal_type="user")
    for r in result["resources"]:
        assert r["principal_type"] == "user"


@pytest.mark.asyncio
async def test_list_filter_by_principal_type_group(seeded_db: AsyncSession, test_user: User) -> None:
    """Filter by principal_type=group returns only group assignments."""
    group = await _create_group(seeded_db, name="pt-filter-group-only")
    svc = RoleAssignmentService(seeded_db, test_user)

    await svc.assign(principal_id=test_user.id, role_name="admin")
    await svc.assign(group_id=group.id, role_name="user")

    result = await svc.list(principal_type="group")
    assert len(result["resources"]) >= 1
    for r in result["resources"]:
        assert r["principal_type"] == "group"


@pytest.mark.asyncio
async def test_list_filter_by_principal_type_service_account(seeded_db: AsyncSession, test_user: User) -> None:
    """Filter by principal_type=service_account returns only service account assignments."""
    project = await _create_project(seeded_db, name="pt-filter-sa-project")
    sa = await _create_service_account(seeded_db, project, created_by=test_user.id, name="pt-filter-sa")
    svc = RoleAssignmentService(seeded_db, test_user)

    await svc.assign(principal_id=test_user.id, role_name="admin")
    await svc.assign(principal_id=sa.id, role_name="project-user", project_id=project.id)

    result = await svc.list(principal_type="service_account")
    assert len(result["resources"]) >= 1
    for r in result["resources"]:
        assert r["principal_type"] == "service_account"


# ============================================================================
# List — filter by scope
# ============================================================================


@pytest.mark.asyncio
async def test_list_filter_by_scope_system(seeded_db: AsyncSession, test_user: User) -> None:
    """Filter by scope=system returns only system-scoped assignments."""
    project = await _create_project(seeded_db, name="scope-filter-project")
    svc = RoleAssignmentService(seeded_db, test_user)

    await svc.assign(principal_id=test_user.id, role_name="admin")
    await svc.assign(principal_id=test_user.id, role_name="project-admin", project_id=project.id)

    result = await svc.list(scope="system")
    for r in result["resources"]:
        assert r["project_id"] is None, f"Expected system scope, got project_id={r['project_id']}"


@pytest.mark.asyncio
async def test_list_filter_by_scope_project(seeded_db: AsyncSession, test_user: User) -> None:
    """Filter by scope=project returns only project-scoped assignments."""
    project = await _create_project(seeded_db, name="scope-filter-proj")
    svc = RoleAssignmentService(seeded_db, test_user)

    await svc.assign(principal_id=test_user.id, role_name="admin")
    await svc.assign(principal_id=test_user.id, role_name="project-admin", project_id=project.id)

    result = await svc.list(scope="project")
    assert len(result["resources"]) >= 1
    for r in result["resources"]:
        assert r["project_id"] is not None, "Expected project scope, got system"
