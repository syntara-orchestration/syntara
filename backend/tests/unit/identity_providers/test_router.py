"""Unit tests for identity_providers router.

Tests cover:
- test_identity_provider endpoint (OIDC connection test)
- delete_identity_provider endpoint (session invalidation, identity cleanup)
- get_identity_provider_service dependency provider
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.identity_providers import router as idp_router
from syntara.identity_providers.models.identity_provider_configuration import (
    OIDCConfiguration,
)
from syntara.identity_providers.router import (
    OIDCTestRequest,
    delete_identity_provider,
    get_identity_provider_service,
)
from syntara.identity_providers.services.oidc_discovery import OIDCTestResult

# ============================================================================
# get_identity_provider_service
# ============================================================================


def test_get_identity_provider_service_returns_service() -> None:
    """Dependency provider wires session, user, and secret service."""
    mock_db = MagicMock()
    mock_user = MagicMock()
    mock_user.id = uuid4()

    with patch("syntara.identity_providers.router.create_secret_service") as mock_create_ss:
        mock_create_ss.return_value = MagicMock()
        service = get_identity_provider_service(mock_db, mock_user)

    mock_create_ss.assert_called_once_with(mock_db)
    assert service.session is mock_db
    assert service.user is mock_user


# ============================================================================
# test_identity_provider endpoint
# ============================================================================


@pytest.mark.asyncio
async def test_oidc_test_endpoint_calls_discovery() -> None:
    """The test endpoint calls test_oidc_connection with the issuer URL."""
    config = OIDCConfiguration(
        issuer_url="https://idp.example.com",
        client_id="test-client",
        client_secret="secret",  # noqa: S106
        redirect_uri="http://localhost/callback",
    )
    request = OIDCTestRequest(name="Test", configuration=config)
    mock_user = MagicMock()
    mock_user.id = uuid4()

    expected_result = OIDCTestResult(
        success=True,
        message="OIDC discovery succeeded",
    )

    with patch(
        "syntara.identity_providers.router.test_oidc_connection",
        new_callable=AsyncMock,
        return_value=expected_result,
    ) as mock_test:
        result = await idp_router.test_identity_provider(request, mock_user)

    mock_test.assert_called_once_with("https://idp.example.com/", disable_tls_verify=False)
    assert result.success is True
    assert result.message == "OIDC discovery succeeded"


@pytest.mark.asyncio
async def test_oidc_test_endpoint_returns_failure() -> None:
    """The test endpoint returns failure result when OIDC discovery fails."""
    config = OIDCConfiguration(
        issuer_url="https://bad-idp.example.com",
        client_id="test-client",
        client_secret="secret",  # noqa: S106
        redirect_uri="http://localhost/callback",
    )
    request = OIDCTestRequest(name="FailTest", configuration=config)
    mock_user = MagicMock()
    mock_user.id = uuid4()

    expected_result = OIDCTestResult(
        success=False,
        message="Connection refused",
    )

    with patch(
        "syntara.identity_providers.router.test_oidc_connection",
        new_callable=AsyncMock,
        return_value=expected_result,
    ):
        result = await idp_router.test_identity_provider(request, mock_user)

    assert result.success is False
    assert result.message == "Connection refused"


# ============================================================================
# delete_identity_provider endpoint
# ============================================================================


@pytest.mark.asyncio
async def test_delete_provider_invalidates_affected_user_tokens() -> None:
    """Delete finds affected users and invalidates their tokens."""
    provider_id = uuid4()
    user_id_1 = uuid4()
    user_id_2 = uuid4()

    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [user_id_1, user_id_2]
    mock_db.exec = AsyncMock(return_value=mock_result)

    mock_service = AsyncMock()
    mock_service.delete_provider = AsyncMock()

    with patch("syntara.identity_providers.router.create_session_store") as mock_store_cls:
        mock_store = AsyncMock()
        mock_store.increment_token_version = AsyncMock()
        mock_store_cls.return_value = mock_store

        await delete_identity_provider(provider_id, mock_service, mock_db)

    mock_service.delete_provider.assert_called_once_with(provider_id)
    assert mock_store.increment_token_version.call_count == 2
    mock_store.increment_token_version.assert_any_call(user_id_1)
    mock_store.increment_token_version.assert_any_call(user_id_2)


@pytest.mark.asyncio
async def test_delete_provider_no_affected_users_skips_token_invalidation() -> None:
    """Delete with no affected users does not open SessionStore."""
    provider_id = uuid4()

    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.exec = AsyncMock(return_value=mock_result)

    mock_service = AsyncMock()
    mock_service.delete_provider = AsyncMock()

    with patch("syntara.identity_providers.router.create_session_store") as mock_store_cls:
        await delete_identity_provider(provider_id, mock_service, mock_db)

    mock_service.delete_provider.assert_called_once_with(provider_id)
    # SessionStore should not be instantiated when there are no affected users
    mock_store_cls.assert_not_called()


@pytest.mark.asyncio
async def test_delete_provider_queries_affected_users_before_delete() -> None:
    """Delete queries for affected user IDs before calling service.delete_provider."""
    provider_id = uuid4()

    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [uuid4()]
    mock_db.exec = AsyncMock(return_value=mock_result)

    call_order: list[str] = []

    mock_service = AsyncMock()

    async def track_delete(*args: object) -> None:
        call_order.append("delete")

    mock_service.delete_provider = AsyncMock(side_effect=track_delete)

    original_exec = mock_db.exec

    async def track_exec(*args: object, **kwargs: object) -> object:
        call_order.append("query")
        return await original_exec(*args, **kwargs)

    mock_db.exec = AsyncMock(side_effect=track_exec)

    with patch("syntara.identity_providers.router.create_session_store") as mock_store_cls:
        mock_store = AsyncMock()
        mock_store.increment_token_version = AsyncMock()
        mock_store_cls.return_value = mock_store

        await delete_identity_provider(provider_id, mock_service, mock_db)

    assert call_order == ["query", "delete"]
