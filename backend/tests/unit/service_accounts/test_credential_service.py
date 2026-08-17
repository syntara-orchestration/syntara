"""Unit tests for ServiceAccountCredentialService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

from syntara.service_accounts.constants import MAX_CREDENTIALS_PER_SA
from syntara.service_accounts.credential_schemas import (
    ServiceAccountCredentialCreateResponse,
    ServiceAccountCredentialListResponse,
    ServiceAccountCredentialRead,
    ServiceAccountCredentialRotateResponse,
)
from syntara.service_accounts.exceptions import (
    CredentialExpirationExceededError,
    CredentialExpirationInPastError,
    ServiceAccountCredentialLimitError,
    ServiceAccountCredentialNotFoundError,
)
from syntara.service_accounts.models.service_account_credential import (
    ServiceAccountCredential,
    ServiceAccountCredentialStatus,
    ServiceAccountCredentialType,
)
from syntara.service_accounts.services.credential_service import ServiceAccountCredentialService


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def mock_user() -> MagicMock:
    """Create a mock user."""
    user = MagicMock()
    user.id = uuid4()
    user.username = "testuser"
    return user


@pytest.fixture
def service(mock_session: AsyncMock, mock_user: MagicMock) -> ServiceAccountCredentialService:
    """Create a ServiceAccountCredentialService with mocked dependencies."""
    return ServiceAccountCredentialService(mock_session, mock_user)


def _mock_count_result(count: int) -> MagicMock:
    """Create a mock exec result returning a count."""
    result = MagicMock()
    result.one.return_value = count
    return result


class TestGenerateCredential:
    """Tests for credential generation."""

    def test_client_credentials_prefix(self) -> None:
        identifier, secret, hashed = ServiceAccountCredentialService._generate_credential(
            ServiceAccountCredentialType.CLIENT_CREDENTIALS
        )
        assert identifier.startswith("nx_sa_")
        assert len(identifier) == 22
        assert len(secret) == 64
        assert hashed.startswith("$argon2id$")


class TestCreateCredential:
    """Tests for credential creation."""

    @pytest.mark.asyncio
    async def test_create_returns_credential_and_secret(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        mock_session.exec.return_value = _mock_count_result(0)
        sa_id = uuid4()
        cred, secret = await service.create_credential(
            service_account_id=sa_id,
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
        )
        assert cred.service_account_id == sa_id
        assert cred.credential_type == ServiceAccountCredentialType.CLIENT_CREDENTIALS
        assert cred.status == ServiceAccountCredentialStatus.ACTIVE
        assert len(secret) > 0

    @pytest.mark.asyncio
    async def test_create_commits_to_database(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        mock_session.exec.return_value = _mock_count_result(0)
        await service.create_credential(
            service_account_id=uuid4(),
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
        )
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_limit(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        mock_session.exec.return_value = _mock_count_result(MAX_CREDENTIALS_PER_SA)
        with pytest.raises(ServiceAccountCredentialLimitError, match="maximum"):
            await service.create_credential(
                service_account_id=uuid4(),
                credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            )


class TestGetCredential:
    """Tests for fetching a credential by ID."""

    @pytest.mark.asyncio
    async def test_get_returns_credential(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        mock_cred = MagicMock(spec=ServiceAccountCredential)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_cred
        mock_session.exec.return_value = mock_result

        result = await service.get_credential(uuid4(), service_account_id=uuid4())
        assert result is mock_cred

    @pytest.mark.asyncio
    async def test_get_raises_not_found(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

        with pytest.raises(ServiceAccountCredentialNotFoundError, match="not found"):
            await service.get_credential(uuid4(), service_account_id=uuid4())

    @pytest.mark.asyncio
    async def test_get_query_filters_by_both_id_and_service_account(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        """Regression: the query must include service_account_id to prevent cross-SA access (BOLA)."""
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = MagicMock(spec=ServiceAccountCredential)
        mock_session.exec.return_value = mock_result

        await service.get_credential(uuid4(), service_account_id=uuid4())

        query = mock_session.exec.call_args[0][0]
        where_str = str(query.whereclause)
        assert "service_account_credentials.id" in where_str
        assert "service_account_credentials.service_account_id" in where_str


class TestDisableCredential:
    """Tests for disabling a credential."""

    @pytest.mark.asyncio
    async def test_disable_sets_status(self, service: ServiceAccountCredentialService, mock_session: AsyncMock) -> None:
        mock_cred = MagicMock(spec=ServiceAccountCredential)
        mock_cred.update_by_user = MagicMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_cred
        mock_session.exec.return_value = mock_result

        await service.disable_credential(uuid4(), service_account_id=uuid4())
        assert mock_cred.status == ServiceAccountCredentialStatus.DISABLED

    @pytest.mark.asyncio
    async def test_disable_raises_not_found(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result
        cred_id, sa_id = uuid4(), uuid4()

        with pytest.raises(ServiceAccountCredentialNotFoundError):
            await service.disable_credential(cred_id, service_account_id=sa_id)


class TestEnableCredential:
    """Tests for enabling a credential."""

    @pytest.mark.asyncio
    async def test_enable_sets_status(self, service: ServiceAccountCredentialService, mock_session: AsyncMock) -> None:
        mock_cred = MagicMock(spec=ServiceAccountCredential)
        mock_cred.update_by_user = MagicMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_cred
        mock_session.exec.return_value = mock_result

        await service.enable_credential(uuid4(), service_account_id=uuid4())
        assert mock_cred.status == ServiceAccountCredentialStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_enable_raises_not_found(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result
        cred_id, sa_id = uuid4(), uuid4()

        with pytest.raises(ServiceAccountCredentialNotFoundError):
            await service.enable_credential(cred_id, service_account_id=sa_id)


class TestDeleteCredential:
    """Tests for hard-deleting a credential."""

    @pytest.mark.asyncio
    async def test_delete_removes_from_session(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        mock_cred = MagicMock(spec=ServiceAccountCredential)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_cred
        mock_session.exec.return_value = mock_result

        await service.delete_credential(uuid4(), service_account_id=uuid4())
        mock_session.delete.assert_called_once_with(mock_cred)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_raises_not_found(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

        with pytest.raises(ServiceAccountCredentialNotFoundError):
            await service.delete_credential(uuid4(), service_account_id=uuid4())


class TestRotateCredential:
    """Tests for rotating a credential's secret."""

    @pytest.mark.asyncio
    async def test_rotate_raises_not_found(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result
        cred_id, sa_id = uuid4(), uuid4()

        with pytest.raises(ServiceAccountCredentialNotFoundError):
            await service.rotate_credential(cred_id, service_account_id=sa_id)


class TestConversionMethods:
    """Tests for to_read, to_create_response, to_rotate_response."""

    def test_to_read(self, service: ServiceAccountCredentialService) -> None:
        cred = ServiceAccountCredential(
            service_account_id=uuid4(),
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            identifier="nx_sa_abcdef1234567890",
            hashed_secret="$argon2id$placeholder",  # noqa: S106
            created_by=uuid4(),
        )
        read = service.to_read(cred)
        assert isinstance(read, ServiceAccountCredentialRead)
        assert read.identifier == "nx_sa_abcdef1234567890"

    def test_to_create_response_client_credentials(self, service: ServiceAccountCredentialService) -> None:
        cred = ServiceAccountCredential(
            service_account_id=uuid4(),
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            identifier="nx_sa_abcdef1234567890",
            hashed_secret="$argon2id$placeholder",  # noqa: S106
            created_by=uuid4(),
        )
        resp = service.to_create_response(cred, "the-secret")
        assert isinstance(resp, ServiceAccountCredentialCreateResponse)
        assert resp.client_secret == "the-secret"  # noqa: S105

    def test_to_rotate_response(self, service: ServiceAccountCredentialService) -> None:
        cred = ServiceAccountCredential(
            service_account_id=uuid4(),
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            identifier="nx_sa_abcdef1234567890",
            hashed_secret="$argon2id$placeholder",  # noqa: S106
            created_by=uuid4(),
        )
        resp = service.to_rotate_response(cred, "new-secret")
        assert isinstance(resp, ServiceAccountCredentialRotateResponse)
        assert resp.client_secret == "new-secret"  # noqa: S105


class TestServiceInheritance:
    """Tests that ServiceAccountCredentialService extends BaseService."""

    def test_extends_base_service(self) -> None:
        from syntara.core.services import BaseService

        assert issubclass(ServiceAccountCredentialService, BaseService)


class TestCredentialMaxLifetime:
    """Tests for configurable credential max lifetime (AAP-80610)."""

    @pytest.mark.asyncio
    async def test_create_rejects_expires_at_in_past(
        self,
        service: ServiceAccountCredentialService,
        mock_session: AsyncMock,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        mock_session.exec.return_value = _mock_count_result(0)
        past = datetime.now(tz=UTC) - timedelta(hours=1)
        sa_id = uuid4()
        with (
            override_settings(sa_credential_max_lifetime_days=180),
            pytest.raises(CredentialExpirationInPastError, match="future"),
        ):
            await service.create_credential(
                service_account_id=sa_id,
                credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                expires_at=past,
            )

    @pytest.mark.asyncio
    async def test_create_rejects_expires_at_in_past_unlimited(
        self,
        service: ServiceAccountCredentialService,
        mock_session: AsyncMock,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        mock_session.exec.return_value = _mock_count_result(0)
        past = datetime.now(tz=UTC) - timedelta(days=5)
        sa_id = uuid4()
        with (
            override_settings(sa_credential_max_lifetime_days=-1),
            pytest.raises(CredentialExpirationInPastError, match="future"),
        ):
            await service.create_credential(
                service_account_id=sa_id,
                credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                expires_at=past,
            )

    @pytest.mark.asyncio
    async def test_create_auto_sets_expires_at_from_setting(
        self,
        service: ServiceAccountCredentialService,
        mock_session: AsyncMock,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        mock_session.exec.return_value = _mock_count_result(0)
        with override_settings(sa_credential_max_lifetime_days=30):
            before = datetime.now(tz=UTC)
            cred, _ = await service.create_credential(
                service_account_id=uuid4(),
                credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            )
            after = datetime.now(tz=UTC)

        assert cred.expires_at is not None
        assert before + timedelta(days=30) <= cred.expires_at <= after + timedelta(days=30)

    @pytest.mark.asyncio
    async def test_create_respects_caller_expires_at_within_limit(
        self,
        service: ServiceAccountCredentialService,
        mock_session: AsyncMock,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        mock_session.exec.return_value = _mock_count_result(0)
        requested = datetime.now(tz=UTC) + timedelta(days=10)
        with override_settings(sa_credential_max_lifetime_days=30):
            cred, _ = await service.create_credential(
                service_account_id=uuid4(),
                credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                expires_at=requested,
            )

        assert cred.expires_at == requested

    @pytest.mark.asyncio
    async def test_create_rejects_expires_at_beyond_limit(
        self,
        service: ServiceAccountCredentialService,
        mock_session: AsyncMock,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        mock_session.exec.return_value = _mock_count_result(0)
        requested = datetime.now(tz=UTC) + timedelta(days=60)
        sa_id = uuid4()
        with (
            override_settings(sa_credential_max_lifetime_days=30),
            pytest.raises(CredentialExpirationExceededError, match="30 days"),
        ):
            await service.create_credential(
                service_account_id=sa_id,
                credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                expires_at=requested,
            )

    @pytest.mark.asyncio
    async def test_create_unlimited_skips_expiry(
        self,
        service: ServiceAccountCredentialService,
        mock_session: AsyncMock,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        mock_session.exec.return_value = _mock_count_result(0)
        with override_settings(sa_credential_max_lifetime_days=-1):
            cred, _ = await service.create_credential(
                service_account_id=uuid4(),
                credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            )

        assert cred.expires_at is None

    @pytest.mark.asyncio
    async def test_create_unlimited_allows_caller_expires_at(
        self,
        service: ServiceAccountCredentialService,
        mock_session: AsyncMock,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        mock_session.exec.return_value = _mock_count_result(0)
        requested = datetime.now(tz=UTC) + timedelta(days=999)
        with override_settings(sa_credential_max_lifetime_days=-1):
            cred, _ = await service.create_credential(
                service_account_id=uuid4(),
                credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                expires_at=requested,
            )

        assert cred.expires_at == requested

    @pytest.mark.asyncio
    async def test_rotate_refreshes_expires_at(
        self,
        service: ServiceAccountCredentialService,
        mock_session: AsyncMock,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        old_expiry = datetime.now(tz=UTC) + timedelta(days=10)
        mock_cred = MagicMock(spec=ServiceAccountCredential)
        mock_cred.credential_type = ServiceAccountCredentialType.CLIENT_CREDENTIALS
        mock_cred.grace_period_seconds = 3600
        mock_cred.hashed_secret = "$argon2id$old"  # noqa: S105
        mock_cred.expires_at = old_expiry
        mock_cred.update_by_user = MagicMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_cred
        mock_session.exec.return_value = mock_result

        with override_settings(sa_credential_max_lifetime_days=90):
            before = datetime.now(tz=UTC)
            await service.rotate_credential(uuid4(), service_account_id=uuid4())
            after = datetime.now(tz=UTC)

        assert mock_cred.expires_at != old_expiry
        assert mock_cred.expires_at is not None
        assert before + timedelta(days=90) <= mock_cred.expires_at <= after + timedelta(days=90)

    @pytest.mark.asyncio
    async def test_rotate_unlimited_clears_expires_at(
        self,
        service: ServiceAccountCredentialService,
        mock_session: AsyncMock,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        mock_cred = MagicMock(spec=ServiceAccountCredential)
        mock_cred.credential_type = ServiceAccountCredentialType.CLIENT_CREDENTIALS
        mock_cred.grace_period_seconds = 3600
        mock_cred.hashed_secret = "$argon2id$old"  # noqa: S105
        mock_cred.update_by_user = MagicMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_cred
        mock_session.exec.return_value = mock_result

        with override_settings(sa_credential_max_lifetime_days=-1):
            await service.rotate_credential(uuid4(), service_account_id=uuid4())

        assert mock_cred.expires_at is None


class TestReadSchemaIncludesRotationField:
    """Tests that ServiceAccountCredentialRead exposes old_secret_valid_until (AAP-82027)."""

    def test_old_secret_valid_until_populated_from_model(self) -> None:
        rotation_expiry = datetime.now(tz=UTC) + timedelta(hours=1)
        cred = ServiceAccountCredential(
            service_account_id=uuid4(),
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            identifier="nx_sa_abcdef1234567890",
            hashed_secret="$argon2id$placeholder",  # noqa: S106
            old_secret_valid_until=rotation_expiry,
            created_by=uuid4(),
        )
        read = ServiceAccountCredentialRead.model_validate(cred)
        assert read.old_secret_valid_until == rotation_expiry

    def test_old_secret_valid_until_none_when_not_rotating(self) -> None:
        cred = ServiceAccountCredential(
            service_account_id=uuid4(),
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            identifier="nx_sa_abcdef1234567890",
            hashed_secret="$argon2id$placeholder",  # noqa: S106
            created_by=uuid4(),
        )
        read = ServiceAccountCredentialRead.model_validate(cred)
        assert read.old_secret_valid_until is None


class TestServiceAccountCredentialListResponse:
    """Tests for ServiceAccountCredentialListResponse schema fields."""

    def test_max_credentials_defaults_to_constant(self) -> None:
        response = ServiceAccountCredentialListResponse(resources=[])
        assert response.max_credentials == MAX_CREDENTIALS_PER_SA

    def test_total_credentials_defaults_to_zero(self) -> None:
        response = ServiceAccountCredentialListResponse(resources=[])
        assert response.total_credentials == 0

    def test_total_credentials_can_be_set(self) -> None:
        response = ServiceAccountCredentialListResponse(resources=[], total_credentials=7)
        assert response.total_credentials == 7


class TestListCredentials:
    """Tests for list_credentials including total_credentials population."""

    @pytest.mark.asyncio
    async def test_list_credentials_sets_total_credentials(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        sa_id = uuid4()
        mock_response = ServiceAccountCredentialListResponse(resources=[])
        with (
            patch.object(service, "list_resources", new=AsyncMock(return_value=mock_response)),
            patch.object(service, "count_resources", new=AsyncMock(return_value=5)) as mock_count,
        ):
            result = await service.list_credentials(service_account_id=sa_id)

        assert result.total_credentials == 5
        mock_count.assert_called_once_with(
            ServiceAccountCredential,
            service_account_id=sa_id,
        )

    @pytest.mark.asyncio
    async def test_list_credentials_passes_filters_to_list_resources(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        sa_id = uuid4()
        mock_response = ServiceAccountCredentialListResponse(resources=[])
        extra_params = [("status", "active")]
        with (
            patch.object(service, "list_resources", new=AsyncMock(return_value=mock_response)) as mock_list,
            patch.object(service, "count_resources", new=AsyncMock(return_value=0)),
        ):
            await service.list_credentials(
                service_account_id=sa_id,
                limit=10,
                query_params_items=extra_params,
            )

        call_kwargs = mock_list.call_args
        passed_params = call_kwargs.kwargs["query_params_items"]
        assert ("service_account_id", str(sa_id)) in passed_params
        assert ("status", "active") in passed_params
        assert call_kwargs.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_list_credentials_count_ignores_filters(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        sa_id = uuid4()
        mock_response = ServiceAccountCredentialListResponse(resources=[])
        with (
            patch.object(service, "list_resources", new=AsyncMock(return_value=mock_response)),
            patch.object(service, "count_resources", new=AsyncMock(return_value=3)) as mock_count,
        ):
            await service.list_credentials(
                service_account_id=sa_id,
                query_params_items=[("status", "active")],
            )

        mock_count.assert_called_once_with(
            ServiceAccountCredential,
            service_account_id=sa_id,
        )

    @pytest.mark.asyncio
    async def test_list_credentials_returns_max_credentials(
        self, service: ServiceAccountCredentialService, mock_session: AsyncMock
    ) -> None:
        mock_response = ServiceAccountCredentialListResponse(resources=[])
        with (
            patch.object(service, "list_resources", new=AsyncMock(return_value=mock_response)),
            patch.object(service, "count_resources", new=AsyncMock(return_value=0)),
        ):
            result = await service.list_credentials(service_account_id=uuid4())

        assert result.max_credentials == MAX_CREDENTIALS_PER_SA
