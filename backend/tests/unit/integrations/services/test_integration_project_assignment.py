"""Unit tests for integration project assignment operations."""

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import AllowedProjectsResult
from syntara.authz.exceptions import ProjectNotFoundError
from syntara.authz.models import Project
from syntara.core.models import User
from syntara.integrations.exceptions import IntegrationNotFoundError, IntegrationScopeError
from syntara.integrations.models.integration import (
    IntegrationCreate,
    IntegrationProjectAssignment,
    IntegrationScope,
    IntegrationType,
    IntegrationUpdate,
)
from syntara.integrations.services.integration_service import IntegrationService


@pytest.fixture(autouse=True)
def _skip_credential_validation() -> Generator[None, None, None]:
    with patch(
        "syntara.integrations.services.integration_service.CREDENTIAL_REQUIRED_TYPES",
        frozenset(),
    ):
        yield


@pytest.fixture
def integration_service(test_db_session: AsyncSession, test_user: User) -> IntegrationService:
    return IntegrationService(test_db_session, test_user)


def _mcp_create(name: str = "Test MCP", **kwargs: object) -> IntegrationCreate:
    defaults: dict[str, object] = {
        "name": name,
        "integration_type": IntegrationType.MCP_SERVER,
        "configuration": {"integration_type": "mcp_server", "base_url": "http://localhost:8080"},
    }
    defaults.update(kwargs)
    return IntegrationCreate(**defaults)


async def _create_project(session: AsyncSession, name: str = "test-project") -> Project:
    project = Project(name=name, description="Test project")
    session.add(project)
    await session.flush()
    return project


class TestAssignProject:
    """Tests for IntegrationService.assign_project."""

    @pytest.mark.asyncio
    async def test_assign_creates_row_and_returns_read_schema(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        project = await _create_project(test_db_session)
        created = await integration_service.create_integration(_mcp_create(scope=IntegrationScope.PROJECT))

        result = await integration_service.assign_project(created.id, project.id)

        assert result.project_id == project.id
        assert result.project_name == project.name
        assert result.created_at is not None

    @pytest.mark.asyncio
    async def test_assign_to_global_scoped_raises_scope_error(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        project = await _create_project(test_db_session)
        created = await integration_service.create_integration(_mcp_create())

        assert created.scope == IntegrationScope.GLOBAL
        with pytest.raises(IntegrationScopeError, match="global-scoped"):
            await integration_service.assign_project(created.id, project.id)

    @pytest.mark.asyncio
    async def test_assign_idempotent(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        project = await _create_project(test_db_session)
        created = await integration_service.create_integration(_mcp_create(scope=IntegrationScope.PROJECT))

        first = await integration_service.assign_project(created.id, project.id)
        second = await integration_service.assign_project(created.id, project.id)

        assert first.project_id == second.project_id
        assert first.created_at == second.created_at

    @pytest.mark.asyncio
    async def test_assign_nonexistent_integration_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        fake_integration_id = uuid4()
        fake_project_id = uuid4()
        with pytest.raises(IntegrationNotFoundError):
            await integration_service.assign_project(fake_integration_id, fake_project_id)

    @pytest.mark.asyncio
    async def test_assign_nonexistent_project_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create(scope=IntegrationScope.PROJECT))
        integration_id = created.id

        fake_project_id = uuid4()
        with pytest.raises(ProjectNotFoundError):
            await integration_service.assign_project(integration_id, fake_project_id)

    @pytest.mark.asyncio
    async def test_assign_soft_deleted_project_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        project = await _create_project(test_db_session)
        created = await integration_service.create_integration(_mcp_create(scope=IntegrationScope.PROJECT))
        integration_id, project_id = created.id, project.id

        project.deleted_at = datetime.now(UTC)
        test_db_session.add(project)
        await test_db_session.flush()

        with pytest.raises(ProjectNotFoundError):
            await integration_service.assign_project(integration_id, project_id)

    @pytest.mark.asyncio
    async def test_assign_multiple_projects(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        project_a = await _create_project(test_db_session, name="project-a")
        project_b = await _create_project(test_db_session, name="project-b")
        created = await integration_service.create_integration(_mcp_create(scope=IntegrationScope.PROJECT))

        await integration_service.assign_project(created.id, project_a.id)
        await integration_service.assign_project(created.id, project_b.id)

        result = await integration_service.list_assigned_projects(created.id)
        assigned_ids = {r.project_id for r in result.resources}
        assert assigned_ids == {project_a.id, project_b.id}


class TestUnassignProject:
    """Tests for IntegrationService.unassign_project."""

    @pytest.mark.asyncio
    async def test_unassign_deletes_row(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        project = await _create_project(test_db_session)
        created = await integration_service.create_integration(_mcp_create(scope=IntegrationScope.PROJECT))
        await integration_service.assign_project(created.id, project.id)

        await integration_service.unassign_project(created.id, project.id)

        result = await integration_service.list_assigned_projects(created.id)
        assert len(result.resources) == 0

    @pytest.mark.asyncio
    async def test_unassign_idempotent(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create(scope=IntegrationScope.PROJECT))

        await integration_service.unassign_project(created.id, uuid4())

    @pytest.mark.asyncio
    async def test_unassign_global_scoped_raises_scope_error(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())
        integration_id = created.id

        assert created.scope == IntegrationScope.GLOBAL
        fake_project_id = uuid4()
        with pytest.raises(IntegrationScopeError, match="global-scoped"):
            await integration_service.unassign_project(integration_id, fake_project_id)

    @pytest.mark.asyncio
    async def test_unassign_nonexistent_integration_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        fake_integration_id = uuid4()
        fake_project_id = uuid4()
        with pytest.raises(IntegrationNotFoundError):
            await integration_service.unassign_project(fake_integration_id, fake_project_id)


class TestListAssignedProjects:
    """Tests for IntegrationService.list_assigned_projects."""

    @pytest.mark.asyncio
    async def test_list_returns_assigned_projects(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        project = await _create_project(test_db_session)
        created = await integration_service.create_integration(_mcp_create(scope=IntegrationScope.PROJECT))
        await integration_service.assign_project(created.id, project.id)

        result = await integration_service.list_assigned_projects(created.id)

        assert len(result.resources) == 1
        assert result.resources[0].project_id == project.id
        assert result.resources[0].project_name == project.name

    @pytest.mark.asyncio
    async def test_list_empty_when_no_assignments(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create(scope=IntegrationScope.PROJECT))

        result = await integration_service.list_assigned_projects(created.id)

        assert len(result.resources) == 0

    @pytest.mark.asyncio
    async def test_list_nonexistent_integration_raises(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        fake_integration_id = uuid4()
        with pytest.raises(IntegrationNotFoundError):
            await integration_service.list_assigned_projects(fake_integration_id)


class TestGetAssignedProjectIds:
    """Tests for IntegrationService._get_assigned_project_ids."""

    @pytest.mark.asyncio
    async def test_batch_fetch_returns_grouped_ids(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        project_a = await _create_project(test_db_session, name="project-a")
        project_b = await _create_project(test_db_session, name="project-b")
        int1 = await integration_service.create_integration(_mcp_create(name="Int 1", scope=IntegrationScope.PROJECT))
        int2 = await integration_service.create_integration(_mcp_create(name="Int 2", scope=IntegrationScope.PROJECT))
        await integration_service.assign_project(int1.id, project_a.id)
        await integration_service.assign_project(int2.id, project_b.id)

        result = await integration_service._get_assigned_project_ids([int1.id, int2.id])

        assert result[int1.id] == [project_a.id]
        assert result[int2.id] == [project_b.id]

    @pytest.mark.asyncio
    async def test_batch_fetch_empty_list_returns_empty_dict(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        result = await integration_service._get_assigned_project_ids([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_batch_fetch_no_assignments_returns_empty(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create(scope=IntegrationScope.PROJECT))

        result = await integration_service._get_assigned_project_ids([created.id])

        assert created.id not in result


class TestProjectIdsOnIntegrationRead:
    """Tests that IntegrationRead.project_ids is populated correctly."""

    @pytest.mark.asyncio
    async def test_get_includes_project_ids(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        project = await _create_project(test_db_session)
        created = await integration_service.create_integration(_mcp_create(scope=IntegrationScope.PROJECT))
        await integration_service.assign_project(created.id, project.id)

        result = await integration_service.get_integration(created.id)

        assert result.project_ids == [project.id]

    @pytest.mark.asyncio
    async def test_get_global_integration_has_empty_project_ids(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        result = await integration_service.get_integration(created.id)

        assert result.project_ids == []

    @pytest.mark.asyncio
    async def test_list_includes_project_ids(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        project = await _create_project(test_db_session)
        created = await integration_service.create_integration(_mcp_create(scope=IntegrationScope.PROJECT))
        await integration_service.assign_project(created.id, project.id)

        response = await integration_service.list_integrations(
            allowed_projects=AllowedProjectsResult(all_projects=True, project_ids=[])
        )

        matching = [r for r in response.resources if r.id == created.id]
        assert len(matching) == 1
        assert matching[0].project_ids == [project.id]


class TestPatchScopeClearing:
    """Tests that changing scope from project to global clears assignments."""

    @pytest.mark.asyncio
    async def test_patch_scope_project_to_global_clears_assignments(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        project = await _create_project(test_db_session)
        created = await integration_service.create_integration(_mcp_create(scope=IntegrationScope.PROJECT))
        await integration_service.assign_project(created.id, project.id)

        await integration_service.update_integration(created.id, IntegrationUpdate(scope=IntegrationScope.GLOBAL))

        rows = await test_db_session.exec(
            select(IntegrationProjectAssignment).where(IntegrationProjectAssignment.integration_id == created.id)
        )
        assert len(rows.all()) == 0

    @pytest.mark.asyncio
    async def test_patch_scope_global_to_project_allowed(
        self, test_db_session: AsyncSession, integration_service: IntegrationService
    ) -> None:
        created = await integration_service.create_integration(_mcp_create())

        result = await integration_service.update_integration(
            created.id, IntegrationUpdate(scope=IntegrationScope.PROJECT)
        )

        assert result.scope == IntegrationScope.PROJECT
