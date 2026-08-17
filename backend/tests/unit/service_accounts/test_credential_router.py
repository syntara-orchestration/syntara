"""Unit tests for credential router endpoint functions."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.service_accounts.credential_router import (
    create_credential,
    delete_credential,
    disable_credential,
    enable_credential,
    get_credential,
    get_credential_service,
    rotate_credential,
)
from syntara.service_accounts.credential_schemas import (
    ServiceAccountCredentialCreate,
    ServiceAccountCredentialCreateResponse,
    ServiceAccountCredentialRead,
    ServiceAccountCredentialRotateRequest,
    ServiceAccountCredentialRotateResponse,
)
from syntara.service_accounts.models.service_account_credential import (
    ServiceAccountCredential,
    ServiceAccountCredentialStatus,
    ServiceAccountCredentialType,
)


@pytest.fixture
def mock_service() -> MagicMock:
    """Create a mock ServiceAccountCredentialService."""
    svc = MagicMock()
    svc.create_credential = AsyncMock()
    svc.get_credential = AsyncMock()
    svc.delete_credential = AsyncMock()
    svc.rotate_credential = AsyncMock()
    svc.disable_credential = AsyncMock()
    svc.enable_credential = AsyncMock()
    return svc


def _make_credential(**kwargs: object) -> ServiceAccountCredential:
    defaults = {
        "service_account_id": uuid4(),
        "credential_type": ServiceAccountCredentialType.CLIENT_CREDENTIALS,
        "identifier": "nx_sa_abcdef1234567890",
        "hashed_secret": "$argon2id$placeholder",
        "created_by": uuid4(),
    }
    defaults.update(kwargs)
    return ServiceAccountCredential(**defaults)


class TestGetCredentialService:
    """Tests for dependency provider."""

    def test_returns_service(self) -> None:
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        service = get_credential_service(mock_db, mock_user)
        assert service.session is mock_db
        assert service.user is mock_user


class TestCreateCredential:
    """Tests for create_credential endpoint."""

    @pytest.mark.asyncio
    async def test_create_returns_create_response(self, mock_service: MagicMock) -> None:
        sa_id = uuid4()
        cred = _make_credential(service_account_id=sa_id)
        secret = "the-plaintext-secret"  # noqa: S105

        mock_service.create_credential.return_value = (cred, secret)
        mock_service.to_create_response.return_value = ServiceAccountCredentialCreateResponse(
            **ServiceAccountCredentialRead.model_validate(cred).model_dump(),
            client_secret=secret,
        )

        request = ServiceAccountCredentialCreate(credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS)
        result = await create_credential(sa_id, request, mock_service)

        assert isinstance(result, ServiceAccountCredentialCreateResponse)
        assert result.client_secret == secret
        mock_service.create_credential.assert_called_once()


class TestGetCredentialEndpoint:
    """Tests for get_credential endpoint."""

    @pytest.mark.asyncio
    async def test_get_returns_read(self, mock_service: MagicMock) -> None:
        sa_id = uuid4()
        cred = _make_credential()
        mock_service.get_credential.return_value = cred
        mock_service.to_read.return_value = ServiceAccountCredentialRead.model_validate(cred)

        result = await get_credential(sa_id, cred.id, mock_service)
        assert isinstance(result, ServiceAccountCredentialRead)
        mock_service.get_credential.assert_called_once_with(cred.id, service_account_id=sa_id)


class TestDeleteCredentialEndpoint:
    """Tests for delete_credential endpoint."""

    @pytest.mark.asyncio
    async def test_delete_calls_service(self, mock_service: MagicMock) -> None:
        sa_id = uuid4()
        cred_id = uuid4()
        await delete_credential(sa_id, cred_id, mock_service)
        mock_service.delete_credential.assert_called_once_with(cred_id, service_account_id=sa_id)


class TestRotateCredentialEndpoint:
    """Tests for rotate_credential endpoint."""

    @pytest.mark.asyncio
    async def test_rotate_returns_response(self, mock_service: MagicMock) -> None:
        sa_id = uuid4()
        cred = _make_credential()
        secret = "new-secret"  # noqa: S105

        mock_service.rotate_credential.return_value = (cred, secret)
        mock_service.to_rotate_response.return_value = ServiceAccountCredentialRotateResponse(
            **ServiceAccountCredentialRead.model_validate(cred).model_dump(),
            client_secret=secret,
        )

        request = ServiceAccountCredentialRotateRequest()
        result = await rotate_credential(sa_id, cred.id, request, mock_service)

        assert isinstance(result, ServiceAccountCredentialRotateResponse)
        mock_service.rotate_credential.assert_called_once_with(
            cred.id,
            service_account_id=sa_id,
            grace_period_seconds=request.grace_period_seconds,
        )


class TestDisableCredentialEndpoint:
    """Tests for disable_credential endpoint."""

    @pytest.mark.asyncio
    async def test_disable_returns_read(self, mock_service: MagicMock) -> None:
        sa_id = uuid4()
        cred = _make_credential()
        cred.status = ServiceAccountCredentialStatus.DISABLED
        mock_service.disable_credential.return_value = cred
        mock_service.to_read.return_value = ServiceAccountCredentialRead.model_validate(cred)

        result = await disable_credential(sa_id, cred.id, mock_service)
        assert isinstance(result, ServiceAccountCredentialRead)
        mock_service.disable_credential.assert_called_once_with(cred.id, service_account_id=sa_id)


class TestEnableCredentialEndpoint:
    """Tests for enable_credential endpoint."""

    @pytest.mark.asyncio
    async def test_enable_returns_read(self, mock_service: MagicMock) -> None:
        sa_id = uuid4()
        cred = _make_credential()
        mock_service.enable_credential.return_value = cred
        mock_service.to_read.return_value = ServiceAccountCredentialRead.model_validate(cred)

        result = await enable_credential(sa_id, cred.id, mock_service)
        assert isinstance(result, ServiceAccountCredentialRead)
        mock_service.enable_credential.assert_called_once_with(cred.id, service_account_id=sa_id)
