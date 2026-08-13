"""Unit tests for the webhook reception router.

Tests cover the get_webhook_caller auth dependency and
the receive_webhook / receive_eda_webhook endpoints with mocked dependencies.
"""

from collections.abc import AsyncIterator, Callable
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.exceptions import InvalidTokenError
from syntara.auth.services.token_service import TokenPayload
from syntara.core.constants import WebhookLimits
from syntara.core.models import User
from syntara.workflows.exceptions import (
    PayloadTooLargeError,
    TemporalUnavailableError,
    TriggerValidationError,
    WebhookAuthenticationRequiredError,
)
from syntara.workflows.models.webhook_trigger import WebhookTrigger
from syntara.workflows.webhook_router import (
    WebhookResponse,
    _check_payload_size,
    get_webhook_caller,
    receive_eda_webhook,
    receive_webhook,
)
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

# ============================================================================
# _check_payload_size tests
# ============================================================================


def _mock_request_with_stream(
    headers: dict[str, str],
    body: bytes,
    *,
    chunk_size: int = 8192,
) -> Mock:
    """Build a mock Request whose .stream() yields *body* in chunks."""
    mock = Mock(spec=Request)
    mock.headers = headers

    async def _stream() -> AsyncIterator[bytes]:
        for i in range(0, len(body), chunk_size):
            yield body[i : i + chunk_size]

    mock.stream = _stream
    return mock


class TestCheckPayloadSize:
    """Test suite for _check_payload_size dependency."""

    async def test_under_limit_passes(self) -> None:
        mock_request = _mock_request_with_stream({"content-length": "1024"}, b"x" * 1024)
        await _check_payload_size(mock_request)

    async def test_over_limit_raises(self) -> None:
        mock_request = Mock(spec=Request)
        oversized = str(WebhookLimits.PAYLOAD_MAX_BYTES + 1)
        mock_request.headers = {"content-length": oversized}

        with pytest.raises(PayloadTooLargeError, match="Payload too large"):
            await _check_payload_size(mock_request)

    async def test_no_content_length_small_body_passes(self) -> None:
        mock_request = _mock_request_with_stream({}, b'{"event": "test"}')
        await _check_payload_size(mock_request)

    async def test_no_content_length_oversized_body_raises(self) -> None:
        mock_request = _mock_request_with_stream({}, b"x" * (WebhookLimits.PAYLOAD_MAX_BYTES + 1))
        with pytest.raises(PayloadTooLargeError, match="Payload too large"):
            await _check_payload_size(mock_request)

    async def test_exact_limit_passes(self) -> None:
        mock_request = _mock_request_with_stream(
            {"content-length": str(WebhookLimits.PAYLOAD_MAX_BYTES)},
            b"x" * WebhookLimits.PAYLOAD_MAX_BYTES,
        )
        await _check_payload_size(mock_request)

    async def test_non_numeric_content_length_raises(self) -> None:
        mock_request = Mock(spec=Request)
        mock_request.headers = {"content-length": "abc"}

        with pytest.raises(TriggerValidationError, match="Invalid Content-Length"):
            await _check_payload_size(mock_request)

    async def test_body_cached_for_downstream(self) -> None:
        payload = b'{"key": "value"}'
        mock_request = _mock_request_with_stream({"content-length": str(len(payload))}, payload)
        await _check_payload_size(mock_request)
        assert mock_request._body == payload


# ============================================================================
# get_webhook_caller tests
# ============================================================================


def _make_sa_payload(sa_id: str | None = None) -> TokenPayload:
    """Build a TokenPayload for a service account."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return TokenPayload(
        sub=sa_id or str(uuid4()),
        iss="https://test",
        aud="orchestrator-api",
        iat=now,
        exp=now,
        token_type="service_account",  # noqa: S106
        preferred_username="test-sa",
    )


def _make_user_payload() -> TokenPayload:
    """Build a TokenPayload for a regular user (not a service account)."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return TokenPayload(
        sub=str(uuid4()),
        iss="https://test",
        aud="orchestrator-api",
        iat=now,
        exp=now,
        token_type="access",  # noqa: S106
        preferred_username="testuser",
    )


class TestGetWebhookCaller:
    """Test suite for the get_webhook_caller auth dependency."""

    async def test_no_credentials_raises_401(self) -> None:
        """Missing Bearer token raises WebhookAuthenticationRequiredError."""
        mock_db = AsyncMock(spec=AsyncSession)
        with pytest.raises(WebhookAuthenticationRequiredError):
            await get_webhook_caller(credentials=None, db=mock_db)

    async def test_invalid_token_raises_401(self) -> None:
        """Invalid/expired token raises WebhookAuthenticationRequiredError."""
        mock_db = AsyncMock(spec=AsyncSession)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid-token")

        with (
            patch("syntara.workflows.webhook_router._get_token_service") as mock_ts,
            pytest.raises(WebhookAuthenticationRequiredError),
        ):
            mock_ts.return_value.decode_token.side_effect = InvalidTokenError
            await get_webhook_caller(credentials=credentials, db=mock_db)

    async def test_non_sa_token_raises_401(self) -> None:
        """User token (not service_account type) raises WebhookAuthenticationRequiredError."""
        mock_db = AsyncMock(spec=AsyncSession)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="user-token")
        user_payload = _make_user_payload()

        with (
            patch("syntara.workflows.webhook_router._get_token_service") as mock_ts,
            patch("syntara.workflows.webhook_router._check_global_revocation") as mock_revoke,
            pytest.raises(WebhookAuthenticationRequiredError),
        ):
            mock_ts.return_value.decode_token.return_value = user_payload
            mock_revoke.return_value = None
            await get_webhook_caller(credentials=credentials, db=mock_db)

    async def test_valid_sa_token_returns_user_and_id(self) -> None:
        """Valid service account token returns (User, sa_id) tuple."""
        mock_db = AsyncMock(spec=AsyncSession)
        sa_id = uuid4()
        sa_payload = _make_sa_payload(str(sa_id))
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-sa-token")
        mock_user = Mock(spec=User)

        with (
            patch("syntara.workflows.webhook_router._get_token_service") as mock_ts,
            patch("syntara.workflows.webhook_router._check_global_revocation") as mock_revoke,
            patch("syntara.workflows.webhook_router._user_from_payload", return_value=mock_user),
        ):
            mock_ts.return_value.decode_token.return_value = sa_payload
            mock_revoke.return_value = None

            user, returned_sa_id = await get_webhook_caller(credentials=credentials, db=mock_db)

            assert user is mock_user
            assert returned_sa_id == sa_id

    async def test_globally_revoked_token_raises(self) -> None:
        """Token that has been globally revoked raises through _check_global_revocation."""
        from syntara.auth.exceptions import TokenGloballyRevokedError

        mock_db = AsyncMock(spec=AsyncSession)
        sa_payload = _make_sa_payload()
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="revoked-token")

        with (
            patch("syntara.workflows.webhook_router._get_token_service") as mock_ts,
            patch("syntara.workflows.webhook_router._check_global_revocation") as mock_revoke,
            pytest.raises(TokenGloballyRevokedError),
        ):
            mock_ts.return_value.decode_token.return_value = sa_payload
            mock_revoke.side_effect = TokenGloballyRevokedError
            await get_webhook_caller(credentials=credentials, db=mock_db)


# ============================================================================
# receive_webhook / receive_eda_webhook endpoint tests
# ============================================================================

_ENDPOINT_PARAMS = [
    pytest.param(receive_webhook, NodeType.WEBHOOK_TRIGGER, "webhook", "test-hook", id="generic"),
    pytest.param(receive_eda_webhook, NodeType.EDA_TRIGGER, "EDA webhook", "eda-hook", id="eda"),
]


def _make_trigger(
    *,
    webhook_path: str = "test-hook",
    trigger_node_id: str = "trigger-1",
    input_schema: dict[str, Any] | None = None,
) -> Mock:
    """Create a mock WebhookTrigger with sensible defaults."""
    trigger = Mock(spec=WebhookTrigger)
    trigger.id = uuid4()
    trigger.webhook_path = webhook_path
    trigger.workflow_id = uuid4()
    trigger.trigger_node_id = trigger_node_id
    trigger.input_schema = input_schema
    trigger.is_enabled = True
    return trigger


def _make_caller() -> tuple[Mock, UUID]:
    """Create a mock (User, sa_id) caller tuple."""
    user = Mock(spec=User)
    sa_id = uuid4()
    return (user, sa_id)


class TestReceiveWebhookEndpoints:
    """Shared tests for receive_webhook and receive_eda_webhook."""

    @pytest.mark.parametrize(("endpoint_fn", "trigger_type", "label", "default_path"), _ENDPOINT_PARAMS)
    async def test_happy_path_returns_webhook_response(
        self, endpoint_fn: Callable[..., Any], trigger_type: str, label: str, default_path: str
    ) -> None:
        """Successful reception creates execution and returns WebhookResponse."""
        mock_db = AsyncMock(spec=AsyncSession)
        trigger = _make_trigger(webhook_path=default_path)
        execution_id = uuid4()
        caller = _make_caller()

        mock_execution = Mock()
        mock_execution.id = execution_id

        with (
            patch("syntara.workflows.webhook_router.WebhookTriggerService") as mock_wts_cls,
            patch("syntara.workflows.webhook_router.ExecutionService") as mock_exec_svc_cls,
            patch("syntara.workflows.webhook_router.AuditEventDispatcher"),
        ):
            mock_wts = AsyncMock()
            mock_wts.get_by_webhook_path = AsyncMock(return_value=trigger)
            mock_wts.verify_service_account_authorization = AsyncMock()
            mock_wts_cls.return_value = mock_wts

            mock_exec_svc = AsyncMock()
            mock_exec_svc.create_execution = AsyncMock(return_value=mock_execution)
            mock_exec_svc_cls.return_value = mock_exec_svc

            result = await endpoint_fn(
                webhook_path=default_path,
                payload={"event": "push"},
                caller=caller,
                temporal_service=AsyncMock(spec=TemporalExecutionService),
                db=mock_db,
                _payload_size=None,
            )

            assert isinstance(result, WebhookResponse)
            assert result.execution_id == execution_id
            assert label in result.message

            mock_wts.verify_service_account_authorization.assert_awaited_once_with(trigger.id, caller[1])

    @pytest.mark.parametrize(("endpoint_fn", "trigger_type", "label", "default_path"), _ENDPOINT_PARAMS)
    async def test_temporal_unavailable_raises_error(
        self, endpoint_fn: Callable[..., Any], trigger_type: str, label: str, default_path: str
    ) -> None:
        """None temporal service raises TemporalUnavailableError."""
        mock_db = AsyncMock(spec=AsyncSession)
        caller = _make_caller()

        with (
            patch("syntara.workflows.webhook_router.WebhookTriggerService") as mock_wts_cls,
            patch("syntara.workflows.webhook_router.AuditEventDispatcher"),
        ):
            mock_wts = AsyncMock()
            mock_wts.get_by_webhook_path = AsyncMock(return_value=_make_trigger(webhook_path=default_path))
            mock_wts.verify_service_account_authorization = AsyncMock()
            mock_wts_cls.return_value = mock_wts

            with pytest.raises(TemporalUnavailableError):
                await endpoint_fn(
                    webhook_path=default_path,
                    payload={"event": "push"},
                    caller=caller,
                    temporal_service=None,
                    db=mock_db,
                    _payload_size=None,
                )

    @pytest.mark.parametrize(("endpoint_fn", "trigger_type", "label", "default_path"), _ENDPOINT_PARAMS)
    async def test_unauthorized_sa_raises_403(
        self, endpoint_fn: Callable[..., Any], trigger_type: str, label: str, default_path: str
    ) -> None:
        """SA not bound to trigger raises WebhookServiceAccountNotAuthorizedError."""
        from syntara.workflows.exceptions import WebhookServiceAccountNotAuthorizedError

        mock_db = AsyncMock(spec=AsyncSession)
        caller = _make_caller()

        with patch("syntara.workflows.webhook_router.WebhookTriggerService") as mock_wts_cls:
            mock_wts = AsyncMock()
            mock_wts.get_by_webhook_path = AsyncMock(return_value=_make_trigger(webhook_path=default_path))
            mock_wts.verify_service_account_authorization = AsyncMock(
                side_effect=WebhookServiceAccountNotAuthorizedError(default_path, trigger_type)
            )
            mock_wts_cls.return_value = mock_wts

            mock_temporal = AsyncMock(spec=TemporalExecutionService)

            with pytest.raises(WebhookServiceAccountNotAuthorizedError):
                await endpoint_fn(
                    webhook_path=default_path,
                    payload={"event": "push"},
                    caller=caller,
                    temporal_service=mock_temporal,
                    db=mock_db,
                    _payload_size=None,
                )

    @pytest.mark.parametrize(("endpoint_fn", "trigger_type", "label", "default_path"), _ENDPOINT_PARAMS)
    async def test_lookup_uses_correct_trigger_type(
        self, endpoint_fn: Callable[..., Any], trigger_type: str, label: str, default_path: str
    ) -> None:
        """Trigger lookup passes the correct trigger_type to the service."""
        mock_db = AsyncMock(spec=AsyncSession)
        caller = _make_caller()
        mock_execution = Mock()
        mock_execution.id = uuid4()

        with (
            patch("syntara.workflows.webhook_router.WebhookTriggerService") as mock_wts_cls,
            patch("syntara.workflows.webhook_router.ExecutionService") as mock_exec_svc_cls,
            patch("syntara.workflows.webhook_router.AuditEventDispatcher"),
        ):
            mock_wts = AsyncMock()
            mock_wts.get_by_webhook_path = AsyncMock(return_value=_make_trigger(webhook_path=default_path))
            mock_wts.verify_service_account_authorization = AsyncMock()
            mock_wts_cls.return_value = mock_wts

            mock_exec_svc = AsyncMock()
            mock_exec_svc.create_execution = AsyncMock(return_value=mock_execution)
            mock_exec_svc_cls.return_value = mock_exec_svc

            await endpoint_fn(
                webhook_path=default_path,
                payload={},
                caller=caller,
                temporal_service=AsyncMock(spec=TemporalExecutionService),
                db=mock_db,
                _payload_size=None,
            )

            mock_wts.get_by_webhook_path.assert_awaited_once_with(default_path, trigger_type=trigger_type)
