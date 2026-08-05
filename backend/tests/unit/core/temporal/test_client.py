"""Unit tests for the shared Temporal client module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from temporalio.service import RPCError, RPCStatusCode

from syntara.core.temporal import client as client_mod
from syntara.core.temporal.client import (
    CONNECTION_ERRORS,
    get_shared_client,
    invalidate_client,
)


@pytest.fixture(autouse=True)
def _reset_client_cache() -> None:
    """Ensure each test starts with a clean client cache."""
    client_mod._cached_client = None


def test_connection_errors_members() -> None:
    assert frozenset({RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED}) == CONNECTION_ERRORS


class TestGetSharedClient:
    """Tests for get_shared_client()."""

    @pytest.mark.asyncio
    async def test_connects_and_caches(self) -> None:
        """First call connects; second call returns the cached instance."""
        mock_client = object()

        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            return_value=mock_client,
        ) as mock_connect:
            first = await get_shared_client()
            second = await get_shared_client()

        assert first is mock_client
        assert second is mock_client
        mock_connect.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exc",
        [
            OSError("connection refused"),
            RuntimeError("event loop closed"),
            RPCError("down", RPCStatusCode.UNAVAILABLE, b""),
        ],
        ids=["OSError", "RuntimeError", "RPCError"],
    )
    async def test_returns_none_on_connect_error(self, exc: Exception) -> None:
        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            side_effect=exc,
        ):
            result = await get_shared_client()

        assert result is None

    @pytest.mark.asyncio
    async def test_does_not_cache_failure(self) -> None:
        """After a failed connect, the next call retries."""
        mock_client = object()

        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            side_effect=[OSError("first attempt"), mock_client],
        ):
            first = await get_shared_client()
            second = await get_shared_client()

        assert first is None
        assert second is mock_client

    @pytest.mark.asyncio
    async def test_uses_settings(self) -> None:
        """Verify address and namespace come from settings."""
        mock_client = object()

        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            return_value=mock_client,
        ) as mock_connect:
            await get_shared_client()

        call_args = mock_connect.call_args
        # First positional arg is the address
        assert call_args[0][0] is not None
        # namespace kwarg is present
        assert "namespace" in call_args[1]
        # tls kwarg is present
        assert "tls" in call_args[1]


class TestInvalidateClient:
    """Tests for invalidate_client()."""

    @pytest.mark.asyncio
    async def test_invalidate_forces_reconnect(self) -> None:
        """After invalidation the next get_shared_client creates a new connection."""
        client_a = object()
        client_b = object()

        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            side_effect=[client_a, client_b],
        ) as mock_connect:
            first = await get_shared_client()
            assert first is client_a
            assert mock_connect.await_count == 1

            invalidate_client()

            second = await get_shared_client()
            assert second is client_b
            assert mock_connect.await_count == 2

    def test_invalidate_is_idempotent(self) -> None:
        """Calling invalidate multiple times without a client is safe."""
        invalidate_client()
        invalidate_client()
        assert client_mod._cached_client is None
