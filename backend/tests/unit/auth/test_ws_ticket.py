"""Unit tests for WebSocket ticket issuance — service account rejection."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.auth.exceptions import ServiceAccountWSTicketError
from syntara.auth.router import create_ws_ticket
from syntara.auth.services.token_service import TokenPayload


def _make_payload(*, token_type: str = "access") -> TokenPayload:  # noqa: S107
    """Build a minimal TokenPayload for testing."""
    now = datetime.now(UTC)
    return TokenPayload(
        sub=str(uuid4()),
        iss="orchestrator",
        iat=now,
        exp=now,
        token_type=token_type,
        preferred_username="test-user",
        email="test@example.com",
        name="Test User",
        given_name="Test",
        family_name="User",
    )


class TestCreateWsTicketServiceAccountRejection:
    """Service account JWTs must be rejected at ws_ticket issuance."""

    @pytest.mark.asyncio
    async def test_service_account_jwt_rejected(self) -> None:
        payload = _make_payload(token_type="service_account")  # noqa: S106
        with pytest.raises(ServiceAccountWSTicketError, match="Service accounts") as exc_info:
            await create_ws_ticket(payload)
        assert exc_info.value.service_account_id == payload.sub

    @pytest.mark.asyncio
    async def test_regular_user_jwt_accepted(self) -> None:
        payload = _make_payload(token_type="access")  # noqa: S106
        with patch("syntara.core.websocket.ticket.get_ticket_client") as mock_get:
            mock_client = MagicMock()
            mock_client.issue_ticket = AsyncMock(return_value=("ticket-abc", 30))
            mock_get.return_value = mock_client
            result = await create_ws_ticket(payload)
        assert result.ticket == "ticket-abc"
        assert result.expires_in == 30
