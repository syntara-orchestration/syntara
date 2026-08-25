"""Unit tests for the shared Temporal client module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from temporalio.client import OutboundInterceptor
from temporalio.service import RPCError, RPCStatusCode

from syntara.core.temporal import client as client_mod
from syntara.core.temporal.client import (
    CONNECTION_ERRORS,
    _TimeoutInterceptor,
    _TimeoutInterceptorFactory,
    build_default_interceptors,
    get_shared_client,
    invalidate_client,
    invalidate_on_connection_error,
)
from syntara.workflows.workflow_engine.client_interceptor import WorkflowAuthClientInterceptor


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


class TestInvalidateOnConnectionError:
    """Tests for invalidate_on_connection_error()."""

    @pytest.mark.asyncio
    async def test_invalidates_on_unavailable(self) -> None:
        mock_client = object()
        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            await get_shared_client()

        assert client_mod._cached_client is not None
        invalidate_on_connection_error(RPCError("down", RPCStatusCode.UNAVAILABLE, b""))
        assert client_mod._cached_client is None

    @pytest.mark.asyncio
    async def test_invalidates_on_deadline_exceeded(self) -> None:
        mock_client = object()
        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            await get_shared_client()

        assert client_mod._cached_client is not None
        invalidate_on_connection_error(RPCError("timeout", RPCStatusCode.DEADLINE_EXCEEDED, b""))
        assert client_mod._cached_client is None

    @pytest.mark.asyncio
    async def test_ignores_non_connection_rpc_error(self) -> None:
        mock_client = object()
        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            await get_shared_client()

        assert client_mod._cached_client is not None
        invalidate_on_connection_error(RPCError("not found", RPCStatusCode.NOT_FOUND, b""))
        assert client_mod._cached_client is not None

    def test_ignores_non_rpc_exception(self) -> None:
        client_mod._cached_client = object()  # type: ignore[assignment]
        invalidate_on_connection_error(ValueError("something else"))
        assert client_mod._cached_client is not None


class TestTimeoutInterceptor:
    """Tests for _TimeoutInterceptor and _TimeoutInterceptorFactory."""

    @dataclass
    class _FakeInput:
        rpc_timeout: timedelta | None = None

    @dataclass
    class _NoTimeoutInput:
        value: int = 0

    def _make_interceptor(self, timeout_s: int = 10) -> _TimeoutInterceptor:
        next_interceptor = Mock()
        next_interceptor.start_workflow = AsyncMock(return_value="handle")
        next_interceptor.cancel_workflow = AsyncMock(return_value=None)
        next_interceptor.query_workflow = AsyncMock(return_value="result")
        return _TimeoutInterceptor(next_interceptor, timedelta(seconds=timeout_s))

    @pytest.mark.asyncio
    async def test_sets_rpc_timeout_when_none(self) -> None:
        interceptor = self._make_interceptor(timeout_s=5)
        rpc_input = self._FakeInput(rpc_timeout=None)

        await interceptor.start_workflow(rpc_input)  # type: ignore[arg-type]

        assert rpc_input.rpc_timeout == timedelta(seconds=5)

    @pytest.mark.asyncio
    async def test_preserves_explicit_rpc_timeout(self) -> None:
        interceptor = self._make_interceptor(timeout_s=5)
        explicit = timedelta(seconds=30)
        rpc_input = self._FakeInput(rpc_timeout=explicit)

        await interceptor.cancel_workflow(rpc_input)  # type: ignore[arg-type]

        assert rpc_input.rpc_timeout == explicit

    @pytest.mark.asyncio
    async def test_skips_input_without_rpc_timeout_attr(self) -> None:
        interceptor = self._make_interceptor()
        rpc_input = self._NoTimeoutInput(value=42)

        await interceptor.query_workflow(rpc_input)  # type: ignore[arg-type]

        assert not hasattr(rpc_input, "rpc_timeout")

    def test_factory_creates_interceptor(self) -> None:
        factory = _TimeoutInterceptorFactory(timedelta(seconds=10))
        next_interceptor = Mock(spec=OutboundInterceptor)

        result = factory.intercept_client(next_interceptor)

        assert isinstance(result, _TimeoutInterceptor)


class TestBuildDefaultInterceptors:
    """Tests for build_default_interceptors()."""

    def test_returns_timeout_and_auth_interceptors(self) -> None:
        """Should return both the RPC timeout and HMAC auth interceptors."""
        interceptors = build_default_interceptors()
        assert len(interceptors) == 2
        assert isinstance(interceptors[0], _TimeoutInterceptorFactory)
        assert isinstance(interceptors[1], WorkflowAuthClientInterceptor)
