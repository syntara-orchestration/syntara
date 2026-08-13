"""Unit tests for the authorization engine.

Tests cover:
- authorize() with mocked authz evaluator
- resolve_allowed_projects() for global and project-scoped access
- resolve_visibility() for unified list-endpoint visibility
- VisibilityResult conversion methods
- assign_project_admin() helper
- assign_authenticated_group_project_user() helper
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import (
    AuthzRequest,
    VisibilityResult,
    assign_authenticated_group_project_user,
    assign_project_admin,
    authorize,
    resolve_allowed_projects,
    resolve_visibility,
)
from syntara.authz.models.project import Project
from syntara.core.models import User
from syntara.core.models.group import Group


@pytest.mark.asyncio
async def test_authorize_allowed(
    seeded_db: AsyncSession,
    test_user: User,
    mock_evaluator: AsyncMock,
) -> None:
    """authorize() returns allowed=True when evaluator allows."""
    request = AuthzRequest(
        user_id=test_user.id,
        action="read",
        resource_type="workflow",
        resource_id="wf-1",
    )
    result = await authorize(seeded_db, mock_evaluator, request)
    assert result.allowed is True
    assert result.denied is False
    assert result.matched_policy == "test-allow"
    mock_evaluator.evaluate.assert_awaited_once()


@pytest.mark.asyncio
async def test_authorize_denied(
    seeded_db: AsyncSession,
    test_user: User,
    mock_evaluator: AsyncMock,
) -> None:
    """authorize() returns denied=True when evaluator denies."""
    mock_evaluator.evaluate.return_value = {
        "allow": False,
        "deny": True,
        "matched_policy": "",
        "denial_reason": "no matching policy",
        "denied_by": "deny-all",
    }
    request = AuthzRequest(
        user_id=test_user.id,
        action="delete",
        resource_type="workflow",
        resource_id="wf-1",
    )
    result = await authorize(seeded_db, mock_evaluator, request)
    assert result.allowed is False
    assert result.denied is True
    assert result.denial_reason == "no matching policy"


@pytest.mark.asyncio
async def test_authorize_with_preresolved_groups(
    seeded_db: AsyncSession,
    test_user: User,
    mock_evaluator: AsyncMock,
) -> None:
    """authorize() uses pre-resolved groups when provided."""
    groups = [{"name": "custom-group", "labels": {}}]
    request = AuthzRequest(
        user_id=test_user.id,
        action="read",
        resource_type="workflow",
        resource_id="wf-1",
        groups=groups,
    )
    result = await authorize(seeded_db, mock_evaluator, request)
    assert result.allowed is True
    # Verify groups were passed to Rego
    call_args = mock_evaluator.evaluate.call_args[0][0]
    assert call_args["groups"] == groups


@pytest.mark.asyncio
async def test_resolve_allowed_projects_global(
    seeded_db: AsyncSession,
    test_user: User,
    mock_evaluator: AsyncMock,
) -> None:
    """resolve_allowed_projects() with '*' returns all_projects=True."""
    result = await resolve_allowed_projects(seeded_db, mock_evaluator, test_user.id, "workflow", "read")
    assert result.all_projects is True
    assert result.project_ids == []


@pytest.mark.asyncio
async def test_resolve_allowed_projects_specific(
    seeded_db: AsyncSession,
    test_user: User,
    mock_evaluator: AsyncMock,
) -> None:
    """resolve_allowed_projects() maps project names to IDs."""
    # Get the default project name
    result = await seeded_db.exec(select(Project).where(Project.name == "default"))
    default_project = result.first()
    assert default_project is not None

    mock_evaluator.evaluate.return_value = {
        "allow": True,
        "deny": False,
        "matched_policy": "test",
        "allowed_projects": ["default"],
    }
    allowed = await resolve_allowed_projects(seeded_db, mock_evaluator, test_user.id, "workflow", "read")
    assert allowed.all_projects is False
    assert default_project.id in allowed.project_ids


@pytest.mark.asyncio
async def test_resolve_allowed_projects_empty(
    seeded_db: AsyncSession,
    test_user: User,
    mock_evaluator: AsyncMock,
) -> None:
    """resolve_allowed_projects() with empty list returns no project IDs."""
    mock_evaluator.evaluate.return_value = {
        "allow": False,
        "deny": False,
        "matched_policy": "",
        "allowed_projects": [],
    }
    allowed = await resolve_allowed_projects(seeded_db, mock_evaluator, test_user.id, "workflow", "read")
    assert allowed.all_projects is False
    assert allowed.project_ids == []


@pytest.mark.asyncio
async def test_assign_project_admin(seeded_db: AsyncSession, test_user: User) -> None:
    """assign_project_admin() creates a project-scoped user role assignment."""
    project = Project(name="admin-test-project", labels={})
    seeded_db.add(project)
    await seeded_db.flush()

    assignment = await assign_project_admin(seeded_db, test_user.id, project.id)
    assert assignment.principal_id == test_user.id
    assert assignment.project_id == project.id
    assert assignment.role_name == "project-admin"


@pytest.mark.asyncio
async def test_assign_authenticated_group_project_user(
    seeded_db: AsyncSession,
) -> None:
    """assign_authenticated_group_project_user() creates group role assignment."""
    project = Project(name="auth-group-test", labels={})
    seeded_db.add(project)
    await seeded_db.flush()

    assignment = await assign_authenticated_group_project_user(seeded_db, project.id)
    assert assignment is not None
    assert assignment.project_id == project.id
    assert assignment.role_name == "project-user"

    group = await seeded_db.get(Group, assignment.group_id)
    assert group is not None
    assert group.name == "authenticated"


@pytest.mark.asyncio
async def test_assign_authenticated_group_missing(test_db_session: AsyncSession) -> None:
    """assign_authenticated_group_project_user() returns None when group missing."""
    # Check whether the 'authenticated' group was pre-seeded (e.g. by CI).
    existing = await test_db_session.exec(select(Group).where(Group.name == "authenticated"))
    if existing.first() is not None:
        pytest.skip("'authenticated' group already seeded; nothing to test")

    result = await assign_authenticated_group_project_user(test_db_session, uuid4())
    assert result is None


# ---------------------------------------------------------------------------
# VisibilityResult unit tests
# ---------------------------------------------------------------------------


class TestVisibilityResult:
    """Tests for VisibilityResult conversion methods."""

    def test_to_allowed_projects_unrestricted(self) -> None:
        result = VisibilityResult(unrestricted=True)
        ap = result.to_allowed_projects()
        assert ap.all_projects is True

    def test_to_allowed_projects_scoped(self) -> None:
        pid = uuid4()
        result = VisibilityResult(unrestricted=False, allowed_project_ids=[pid])
        ap = result.to_allowed_projects()
        assert ap.all_projects is False
        assert ap.project_ids == [pid]

    def test_to_id_restriction_unrestricted(self) -> None:
        result = VisibilityResult(unrestricted=True)
        assert result.to_id_restriction() is None

    def test_to_id_restriction_no_self_scope(self) -> None:
        result = VisibilityResult(unrestricted=False, has_self_scope=False)
        assert result.to_id_restriction() == []

    def test_to_id_restriction_self_scope_user(self) -> None:
        uid = uuid4()
        result = VisibilityResult(has_self_scope=True, self_user_id=uid)
        assert result.to_id_restriction() == [uid]

    def test_to_id_restriction_self_scope_groups(self) -> None:
        gid1, gid2 = uuid4(), uuid4()
        result = VisibilityResult(has_self_scope=True, self_user_id=uuid4(), self_group_ids=[gid1, gid2])
        assert result.to_id_restriction(use_group_ids=True) == [gid1, gid2]

    def test_to_id_restriction_self_scope_no_user_id(self) -> None:
        result = VisibilityResult(has_self_scope=True, self_user_id=None)
        assert result.to_id_restriction() == []


# ---------------------------------------------------------------------------
# resolve_visibility() tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_visibility_unrestricted(
    seeded_db: AsyncSession,
    test_user: User,
    mock_evaluator: AsyncMock,
) -> None:
    """resolve_visibility() returns unrestricted=True when Rego returns '*'."""
    result = await resolve_visibility(seeded_db, mock_evaluator, test_user.id, "workflow", "read")
    assert result.unrestricted is True


@pytest.mark.asyncio
async def test_resolve_visibility_project_scoped(
    seeded_db: AsyncSession,
    test_user: User,
    mock_evaluator: AsyncMock,
) -> None:
    """resolve_visibility() maps project names to IDs."""
    proj_result = await seeded_db.exec(select(Project).where(Project.name == "default"))
    default_project = proj_result.first()
    assert default_project is not None

    mock_evaluator.evaluate.return_value = {
        "allow": True,
        "allowed_projects": ["default"],
    }
    result = await resolve_visibility(seeded_db, mock_evaluator, test_user.id, "workflow", "read")
    assert result.unrestricted is False
    assert default_project.id in result.allowed_project_ids


@pytest.mark.asyncio
async def test_resolve_visibility_self_scope(
    seeded_db: AsyncSession,
    test_user: User,
    mock_evaluator: AsyncMock,
) -> None:
    """resolve_visibility() detects self-scope policies in effective policies."""
    mock_evaluator.evaluate.return_value = {
        "allow": True,
        "allowed_projects": [],
    }
    result = await resolve_visibility(seeded_db, mock_evaluator, test_user.id, "user", "read")
    assert result.unrestricted is False
    assert result.has_self_scope is True
    assert result.self_user_id == test_user.id


@pytest.mark.asyncio
async def test_resolve_visibility_no_access(
    seeded_db: AsyncSession,
    test_user: User,
    mock_evaluator: AsyncMock,
) -> None:
    """resolve_visibility() returns empty result when no policies match."""
    mock_evaluator.evaluate.return_value = {
        "allow": False,
        "allowed_projects": [],
    }
    result = await resolve_visibility(seeded_db, mock_evaluator, test_user.id, "nonexistent", "read")
    assert result.unrestricted is False
    assert result.allowed_project_ids == []
    assert result.has_self_scope is False
    assert result.self_user_id is None
