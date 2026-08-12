"""Unit tests for WebSocketTicketClient."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from syntara.core.websocket.ticket import WebSocketTicketClient


def _mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.cache_host = "localhost"
    mock.cache_port = 6379
    mock.cache_db = 0
    mock.cache_password = None
    mock.cache_connection_pool_size = 5
    return mock


def _make_client() -> tuple[WebSocketTicketClient, AsyncMock]:
    with patch("syntara.core.cache.base.get_settings", return_value=_mock_settings()):
        client = WebSocketTicketClient()
    mock_redis = AsyncMock()
    client._client = mock_redis
    return client, mock_redis


_USER_ID = uuid4()
_PAYLOAD = json.dumps(
    {
        "user_id": str(_USER_ID),
        "username": "alice",
        "email": "alice@example.com",
        "first_name": "Alice",
        "last_name": "Smith",
    }
)


class TestIssueTicket:
    """Tests for WebSocketTicketClient.issue_ticket."""

    @pytest.mark.anyio
    async def test_returns_ticket_and_ttl(self) -> None:
        client, mock_redis = _make_client()
        ticket, ttl = await client.issue_ticket(
            user_id=_USER_ID,
            username="alice",
            email="alice@example.com",
            first_name="Alice",
            last_name="Smith",
        )
        assert isinstance(ticket, str)
        assert len(ticket) > 20
        assert ttl > 0
        mock_redis.setex.assert_awaited_once()


class TestRedeemTicket:
    """Tests for WebSocketTicketClient.redeem_ticket."""

    @pytest.mark.anyio
    async def test_issue_then_redeem_returns_correct_user(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.get.return_value = _PAYLOAD
        mock_redis.delete.return_value = 1

        user = await client.redeem_ticket("some-ticket")

        assert user is not None
        assert user.id == _USER_ID
        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert user.first_name == "Alice"
        mock_redis.get.assert_awaited_once()
        mock_redis.delete.assert_awaited_once()

    @pytest.mark.anyio
    async def test_expired_ticket_returns_none(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.get.return_value = None

        user = await client.redeem_ticket("expired-ticket")

        assert user is None

    @pytest.mark.anyio
    async def test_double_redeem_returns_none_on_second(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.get.side_effect = [_PAYLOAD, None]
        mock_redis.delete.return_value = 1

        first = await client.redeem_ticket("one-time-ticket")
        second = await client.redeem_ticket("one-time-ticket")

        assert first is not None
        assert first.username == "alice"
        assert second is None

    @pytest.mark.anyio
    async def test_garbage_ticket_returns_none(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.get.return_value = None

        user = await client.redeem_ticket("!@#$%^&*()_garbage")

        assert user is None

    @pytest.mark.anyio
    async def test_corrupt_json_returns_none(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.get.return_value = "not-valid-json{{"
        mock_redis.delete.return_value = 1

        user = await client.redeem_ticket("corrupt-ticket")

        assert user is None

    @pytest.mark.anyio
    async def test_user_id_preserved_as_uuid(self) -> None:
        client, mock_redis = _make_client()
        mock_redis.get.return_value = _PAYLOAD
        mock_redis.delete.return_value = 1

        user = await client.redeem_ticket("uuid-ticket")

        assert user is not None
        assert isinstance(user.id, UUID)
        assert user.id == _USER_ID
