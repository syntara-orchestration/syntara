"""Unit tests for ServiceAccountService."""

from __future__ import annotations

from datetime import UTC
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from syntara.service_accounts.exceptions import ServiceAccountNameConflictError, ServiceAccountNotFoundError
from syntara.service_accounts.models.service_account import ServiceAccount, ServiceAccountStatus
from syntara.service_accounts.schemas import ServiceAccountListResponse, ServiceAccountRead
from syntara.service_accounts.services.service_account_service import ServiceAccountService


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_user() -> MagicMock:
    """Create a mock user."""
    user = MagicMock()
    user.id = uuid4()
    user.username = "testuser"
    return user


@pytest.fixture
def service(mock_session: AsyncMock, mock_user: MagicMock) -> ServiceAccountService:
    """Create a ServiceAccountService with mocked dependencies."""
    return ServiceAccountService(mock_session, mock_user)


class TestCreateServiceAccount:
    """Tests for service account creation."""

    @pytest.mark.asyncio
    async def test_create_returns_service_account(self, service: ServiceAccountService) -> None:
        sa = await service.create_service_account(
            name="CI Pipeline",
            project_id=uuid4(),
            description="For CI/CD",
        )
        assert sa.name == "CI Pipeline"
        assert sa.description == "For CI/CD"
        assert sa.status == ServiceAccountStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_create_sets_created_by(self, service: ServiceAccountService, mock_user: MagicMock) -> None:
        sa = await service.create_service_account(
            name="test",
            project_id=uuid4(),
        )
        assert sa.created_by == mock_user.id

    @pytest.mark.asyncio
    async def test_create_commits_to_database(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        await service.create_service_account(name="test", project_id=uuid4())
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_name_conflict(
        self, service: ServiceAccountService, mock_session: AsyncMock
    ) -> None:
        error = IntegrityError("", {}, Exception("service_accounts_name"))
        mock_session.flush.side_effect = error
        with pytest.raises(ServiceAccountNameConflictError, match="already exists"):
            await service.create_service_account(name="duplicate", project_id=uuid4())

    @pytest.mark.asyncio
    async def test_create_description_defaults_none(self, service: ServiceAccountService) -> None:
        sa = await service.create_service_account(name="test", project_id=uuid4())
        assert sa.description is None


class TestGetServiceAccount:
    """Tests for fetching a service account by ID."""

    @pytest.mark.asyncio
    async def test_get_returns_service_account(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        sa_id = uuid4()
        mock_sa = MagicMock(spec=ServiceAccount)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_sa
        mock_session.exec.return_value = mock_result

        result = await service.get_service_account(sa_id)
        assert result is mock_sa

    @pytest.mark.asyncio
    async def test_get_raises_not_found(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

        with pytest.raises(ServiceAccountNotFoundError, match="not found"):
            await service.get_service_account(uuid4())


class TestUpdateServiceAccount:
    """Tests for updating a service account."""

    @pytest.mark.asyncio
    async def test_update_name(
        self, service: ServiceAccountService, mock_session: AsyncMock, mock_user: MagicMock
    ) -> None:
        mock_sa = MagicMock(spec=ServiceAccount)
        mock_sa.update_by_user = MagicMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_sa
        mock_session.exec.return_value = mock_result

        await service.update_service_account(uuid4(), name="Updated Name")
        assert mock_sa.name == "Updated Name"
        mock_sa.update_by_user.assert_called_once_with(mock_user.id)

    @pytest.mark.asyncio
    async def test_update_description(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        mock_sa = MagicMock(spec=ServiceAccount)
        mock_sa.update_by_user = MagicMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_sa
        mock_session.exec.return_value = mock_result

        await service.update_service_account(uuid4(), description="New desc")
        assert mock_sa.description == "New desc"

    @pytest.mark.asyncio
    async def test_update_no_changes_when_none(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        mock_sa = MagicMock(spec=ServiceAccount)
        mock_sa.name = "Original"
        mock_sa.description = "Original desc"
        mock_sa.update_by_user = MagicMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_sa
        mock_session.exec.return_value = mock_result

        await service.update_service_account(uuid4())
        assert mock_sa.name == "Original"
        assert mock_sa.description == "Original desc"

    @pytest.mark.asyncio
    async def test_update_raises_not_found(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

        with pytest.raises(ServiceAccountNotFoundError):
            await service.update_service_account(uuid4(), name="test")


class TestDeleteServiceAccount:
    """Tests for hard-deleting a service account."""

    @pytest.mark.asyncio
    async def test_delete_hard_deletes_with_cleanup(
        self, service: ServiceAccountService, mock_session: AsyncMock, mock_user: MagicMock
    ) -> None:
        mock_sa = MagicMock(spec=ServiceAccount)
        mock_sa.name = "TestSA"
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_sa
        mock_session.exec.return_value = mock_result

        await service.delete_service_account(uuid4())

        # 3 exec calls: select SA, credential delete, role assignment delete
        assert mock_session.exec.call_count == 3
        mock_session.delete.assert_called_once_with(mock_sa)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_cleans_credentials_and_non_builtin_roles(
        self, service: ServiceAccountService, mock_session: AsyncMock, mock_user: MagicMock
    ) -> None:
        """Verify credential deletion and is_builtin filter on role assignment cleanup."""
        mock_sa = MagicMock(spec=ServiceAccount)
        mock_sa.name = "TestSA"
        sa_id = uuid4()
        mock_sa.id = sa_id
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_sa
        mock_session.exec.return_value = mock_result

        await service.delete_service_account(sa_id)

        # Inspect the delete statements passed to exec
        exec_calls = mock_session.exec.call_args_list
        # Call 0: select SA, Call 1: credential delete, Call 2: role delete
        assert len(exec_calls) == 3

        # Verify credential delete targets the SA's credentials
        cred_delete_stmt = exec_calls[1][0][0]
        assert "service_account_credentials" in str(cred_delete_stmt)

        # Verify role assignment delete includes is_builtin filter
        role_delete_stmt = exec_calls[2][0][0]
        role_stmt_str = str(role_delete_stmt)
        assert "role_assignments" in role_stmt_str
        assert "is_builtin" in role_stmt_str

    @pytest.mark.asyncio
    async def test_delete_raises_not_found(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

        with pytest.raises(ServiceAccountNotFoundError):
            await service.delete_service_account(uuid4())


class TestDisableServiceAccount:
    """Tests for disabling a service account."""

    @pytest.mark.asyncio
    async def test_disable_sets_status(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        mock_sa = MagicMock(spec=ServiceAccount)
        mock_sa.update_by_user = MagicMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_sa
        mock_session.exec.return_value = mock_result

        await service.disable_service_account(uuid4())
        assert mock_sa.status == ServiceAccountStatus.DISABLED

    @pytest.mark.asyncio
    async def test_disable_raises_not_found(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

        with pytest.raises(ServiceAccountNotFoundError):
            await service.disable_service_account(uuid4())


class TestEnableServiceAccount:
    """Tests for enabling a service account."""

    @pytest.mark.asyncio
    async def test_enable_sets_status(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        mock_sa = MagicMock(spec=ServiceAccount)
        mock_sa.update_by_user = MagicMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_sa
        mock_session.exec.return_value = mock_result

        await service.enable_service_account(uuid4())
        assert mock_sa.status == ServiceAccountStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_enable_raises_not_found(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

        with pytest.raises(ServiceAccountNotFoundError):
            await service.enable_service_account(uuid4())


class TestToReadConversion:
    """Tests for model-to-schema conversion."""

    @pytest.mark.asyncio
    async def test_to_read_returns_read_schema(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        sa = ServiceAccount(
            name="test",
            project_id=uuid4(),
            created_by=uuid4(),
        )
        # Mock the project name resolution
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.exec.return_value = mock_result

        read = await service.to_read(sa)
        assert isinstance(read, ServiceAccountRead)
        assert read.name == "test"

    @pytest.mark.asyncio
    async def test_to_read_includes_project_name(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        project_id = uuid4()
        sa = ServiceAccount(name="test", project_id=project_id, created_by=uuid4())

        mock_result = MagicMock()
        mock_result.first.return_value = ("My Project", None)
        mock_session.exec.return_value = mock_result

        read = await service.to_read(sa)
        assert read.project_name == "My Project"
        assert read.is_project_deleted is False

    @pytest.mark.asyncio
    async def test_to_read_marks_deleted_project(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        from datetime import datetime

        project_id = uuid4()
        sa = ServiceAccount(name="test", project_id=project_id, created_by=uuid4())

        mock_result = MagicMock()
        mock_result.first.return_value = ("Old Project", datetime(2026, 1, 1, tzinfo=UTC))
        mock_session.exec.return_value = mock_result

        read = await service.to_read(sa)
        assert read.project_name == "Old Project"
        assert read.is_project_deleted is True

    @pytest.mark.asyncio
    async def test_to_read_handles_missing_project(
        self, service: ServiceAccountService, mock_session: AsyncMock
    ) -> None:
        project_id = uuid4()
        sa = ServiceAccount(name="test", project_id=project_id, created_by=uuid4())

        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.exec.return_value = mock_result

        read = await service.to_read(sa)
        assert read.project_name is None


class TestResolveProjectInfosBatch:
    """Tests for batch project info resolution (_resolve_project_infos)."""

    @pytest.mark.asyncio
    async def test_returns_empty_dict_for_empty_input(
        self, service: ServiceAccountService, mock_session: AsyncMock
    ) -> None:
        result = await service._resolve_project_infos(set())
        assert result == {}
        mock_session.exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolves_multiple_projects(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        proj_a = uuid4()
        proj_b = uuid4()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (proj_a, "Project A", None),
            (proj_b, "Project B", None),
        ]
        mock_session.exec.return_value = mock_result

        result = await service._resolve_project_infos({proj_a, proj_b})
        assert result[proj_a] == ("Project A", False)
        assert result[proj_b] == ("Project B", False)

    @pytest.mark.asyncio
    async def test_marks_deleted_projects(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        from datetime import datetime

        proj_id = uuid4()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (proj_id, "Deleted Project", datetime(2026, 1, 1, tzinfo=UTC)),
        ]
        mock_session.exec.return_value = mock_result

        result = await service._resolve_project_infos({proj_id})
        assert result[proj_id] == ("Deleted Project", True)

    @pytest.mark.asyncio
    async def test_missing_projects_omitted(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        existing = uuid4()
        missing = uuid4()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (existing, "Exists", None),
        ]
        mock_session.exec.return_value = mock_result

        result = await service._resolve_project_infos({existing, missing})
        assert existing in result
        assert missing not in result


class TestListServiceAccounts:
    """Tests for listing service accounts with project info resolution."""

    @pytest.mark.asyncio
    async def test_list_resolves_project_info(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        proj_id = uuid4()
        sa_read = ServiceAccountRead(
            id=uuid4(),
            name="sa-1",
            status=ServiceAccountStatus.ACTIVE,
            project_id=proj_id,
            created_by=uuid4(),
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        mock_response = ServiceAccountListResponse(resources=[sa_read], next=None)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(service, "list_resources", AsyncMock(return_value=mock_response))

            mock_result = MagicMock()
            mock_result.all.return_value = [(proj_id, "My Project", None)]
            mock_session.exec.return_value = mock_result

            response = await service.list_service_accounts()

        assert response.resources[0].project_name == "My Project"
        assert response.resources[0].is_project_deleted is False

    @pytest.mark.asyncio
    async def test_list_marks_deleted_project(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        from datetime import datetime

        proj_id = uuid4()
        sa_read = ServiceAccountRead(
            id=uuid4(),
            name="sa-1",
            status=ServiceAccountStatus.ACTIVE,
            project_id=proj_id,
            created_by=uuid4(),
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        mock_response = ServiceAccountListResponse(resources=[sa_read], next=None)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(service, "list_resources", AsyncMock(return_value=mock_response))

            mock_result = MagicMock()
            mock_result.all.return_value = [(proj_id, "Old Project", datetime(2026, 1, 1, tzinfo=UTC))]
            mock_session.exec.return_value = mock_result

            response = await service.list_service_accounts()

        assert response.resources[0].project_name == "Old Project"
        assert response.resources[0].is_project_deleted is True

    @pytest.mark.asyncio
    async def test_list_handles_missing_project(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        proj_id = uuid4()
        sa_read = ServiceAccountRead(
            id=uuid4(),
            name="sa-1",
            status=ServiceAccountStatus.ACTIVE,
            project_id=proj_id,
            created_by=uuid4(),
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        mock_response = ServiceAccountListResponse(resources=[sa_read], next=None)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(service, "list_resources", AsyncMock(return_value=mock_response))

            mock_result = MagicMock()
            mock_result.all.return_value = []
            mock_session.exec.return_value = mock_result

            response = await service.list_service_accounts()

        assert response.resources[0].project_name is None
        assert response.resources[0].is_project_deleted is False

    @pytest.mark.asyncio
    async def test_list_empty_resources(self, service: ServiceAccountService, mock_session: AsyncMock) -> None:
        mock_response = ServiceAccountListResponse(resources=[], next=None)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(service, "list_resources", AsyncMock(return_value=mock_response))

            response = await service.list_service_accounts()

        assert response.resources == []
        mock_session.exec.assert_not_called()


class TestServiceAccountServiceInheritance:
    """Tests that ServiceAccountService extends BaseService."""

    def test_extends_base_service(self) -> None:
        from syntara.core.services import BaseService

        assert issubclass(ServiceAccountService, BaseService)
