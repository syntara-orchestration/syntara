"""Unit tests for the shared Temporal client module."""

from __future__ import annotations

import asyncio
import gc
import weakref
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.service import RPCError, RPCStatusCode

import syntara.core.temporal.client as client_mod
from syntara.core.config.base import get_settings
from syntara.core.temporal.client import (
    CONNECTION_ERRORS,
    get_shared_client,
    invalidate_client,
    invalidate_on_connection_error,
)

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def _reset_client_cache() -> Generator[None]:
    """Ensure each test starts and ends with a clean client cache."""

    def _clear() -> None:
        for task in {client_mod._connect_task, *client_mod._pending_connect_tasks}:
            if task is not None and not task.done():
                task.cancel()
        client_mod._pending_connect_tasks.clear()
        client_mod._cached_client = None
        client_mod._connect_task = None
        client_mod._connect_started_at = None

    _clear()
    yield
    _clear()


def test_connection_errors_members() -> None:
    assert frozenset({RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED}) == CONNECTION_ERRORS


class TestGetSharedClient:
    """Tests for get_shared_client() caching and hardened connect handling."""

    async def test_returns_cached_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return the cached client without reconnecting."""
        sentinel = MagicMock()
        monkeypatch.setattr(client_mod, "_cached_client", sentinel)
        result = await get_shared_client()
        assert result is sentinel

    async def test_connects_and_caches(self) -> None:
        """First call connects; second call returns the cached instance."""
        mock_client = MagicMock()

        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            return_value=mock_client,
        ) as mock_connect:
            first = await get_shared_client()
            second = await get_shared_client()

        assert first is mock_client
        assert second is mock_client
        assert client_mod._cached_client is mock_client
        mock_connect.assert_awaited_once()

    @pytest.mark.parametrize(
        "exc",
        [
            OSError("connection refused"),
            RuntimeError("event loop closed"),
            RPCError("down", RPCStatusCode.UNAVAILABLE, b""),
            TimeoutError("connect timed out"),
        ],
        ids=["OSError", "RuntimeError", "RPCError", "TimeoutError"],
    )
    async def test_returns_none_on_connect_error(self, exc: Exception) -> None:
        """Should return None when Temporal is unreachable."""
        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            side_effect=exc,
        ):
            result = await get_shared_client()

        assert result is None

    async def test_does_not_cache_failure(self) -> None:
        """After a failed connect, the next call retries."""
        mock_client = MagicMock()

        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            side_effect=[OSError("first attempt"), mock_client],
        ):
            first = await get_shared_client()
            second = await get_shared_client()

        assert first is None
        assert second is mock_client

    async def test_uses_settings(self) -> None:
        """Verify address and namespace come from settings."""
        mock_client = MagicMock()

        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            return_value=mock_client,
        ) as mock_connect:
            await get_shared_client()

        settings = get_settings()
        call_args = mock_connect.call_args
        # First positional arg is the configured address
        assert call_args[0][0] == settings.temporal_address
        # namespace kwarg comes from settings
        assert call_args[1]["namespace"] == settings.temporal_namespace
        # tls kwarg is present
        assert "tls" in call_args[1]

    async def test_hung_connect_does_not_hold_client_lock(self) -> None:
        """Client.connect must not hold ``_client_lock`` while it is in flight."""
        connect_started = asyncio.Event()

        async def _hang(*_args: object, **_kwargs: object) -> MagicMock:
            connect_started.set()
            await asyncio.Event().wait()
            return MagicMock()

        with patch(
            "syntara.core.temporal.client.Client.connect",
            new=_hang,
        ):
            waiter = asyncio.create_task(get_shared_client())
            await asyncio.wait_for(connect_started.wait(), timeout=1.0)
            assert not client_mod._client_lock.locked()
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.05):
                    await get_shared_client()
            assert client_mod._connect_task is not None
            assert not client_mod._connect_task.done()
            assert not waiter.done()
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)

    async def test_invalidate_does_not_drop_in_flight_connect_task(self) -> None:
        """Clearing the cache must not drop the strong ref to an in-flight connect."""
        connect_started = asyncio.Event()
        connect_calls = 0

        async def _hang(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            connect_started.set()
            await asyncio.Event().wait()
            return MagicMock()

        with patch(
            "syntara.core.temporal.client.Client.connect",
            new=_hang,
        ):
            waiter = asyncio.create_task(get_shared_client())
            await asyncio.wait_for(connect_started.wait(), timeout=1.0)
            in_flight = client_mod._connect_task
            assert in_flight is not None
            invalidate_client()
            later_waiter = asyncio.create_task(get_shared_client())
            await asyncio.sleep(0.05)
            assert client_mod._connect_task is in_flight
            assert not in_flight.done()
            assert connect_calls == 1
            waiter.cancel()
            later_waiter.cancel()
            await asyncio.gather(waiter, later_waiter, return_exceptions=True)

    async def test_invalidate_after_successful_connect_reconnects(self) -> None:
        """A finished connect task must not block reconnect after cache invalidation."""
        first_client = MagicMock()
        second_client = MagicMock()
        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            side_effect=[first_client, second_client],
        ) as mock_connect:
            assert await get_shared_client() is first_client
            invalidate_client()
            assert client_mod._cached_client is None
            assert await get_shared_client() is second_client
            assert mock_connect.await_count == 2

    async def test_timed_out_waiter_does_not_cancel_overlapping_sibling(self) -> None:
        """A waiter timeout must leave the shared connect running for later waiters."""
        connect_started = asyncio.Event()
        allow_connect = asyncio.Event()
        client = MagicMock()
        connect_calls = 0

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            connect_started.set()
            await allow_connect.wait()
            return client

        with (
            patch(
                "syntara.core.temporal.client.Client.connect",
                new=_connect,
            ),
            patch("syntara.core.temporal.client.CONNECT_TIMEOUT_SECONDS", 0.25),
        ):
            try:
                first = asyncio.create_task(get_shared_client())
                await asyncio.wait_for(connect_started.wait(), timeout=1.0)
                await asyncio.sleep(0.05)
                second = asyncio.create_task(get_shared_client())
                in_flight = client_mod._connect_task
                assert in_flight is not None
                assert await asyncio.wait_for(first, timeout=1.0) is None
                assert not in_flight.done()
                assert not in_flight.cancelled()
                assert client_mod._connect_task is in_flight
                assert connect_calls == 1
                allow_connect.set()
                assert await asyncio.wait_for(second, timeout=1.0) is client
                assert client_mod._cached_client is client
            finally:
                allow_connect.set()

    async def test_stale_replacement_does_not_cancel_joined_waiters(self) -> None:
        """Replacing a stale connect must not cancel waiters still joined to it."""
        connect_started = asyncio.Event()
        replacement_started = asyncio.Event()
        allow_first = asyncio.Event()
        first_client = MagicMock(name="original")
        second_client = MagicMock(name="replacement")
        connect_calls = 0

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            if connect_calls == 1:
                connect_started.set()
                await allow_first.wait()
                return first_client
            replacement_started.set()
            return second_client

        with (
            patch(
                "syntara.core.temporal.client.Client.connect",
                new=_connect,
            ),
            patch("syntara.core.temporal.client.CONNECT_TIMEOUT_SECONDS", 0.4),
        ):
            try:
                first = asyncio.create_task(get_shared_client())
                await asyncio.wait_for(connect_started.wait(), timeout=1.0)
                await asyncio.sleep(0.05)
                sibling = asyncio.create_task(get_shared_client())
                original = client_mod._connect_task
                assert original is not None
                assert await asyncio.wait_for(first, timeout=1.0) is None
                third = asyncio.create_task(get_shared_client())
                await asyncio.wait_for(replacement_started.wait(), timeout=1.0)
                assert connect_calls == 2
                assert client_mod._connect_task is not original
                assert not original.cancelled()
                allow_first.set()
                assert await asyncio.wait_for(sibling, timeout=1.0) is not None
                assert await asyncio.wait_for(third, timeout=1.0) is not None
                assert connect_calls == 2
            finally:
                allow_first.set()

    async def test_late_connect_success_is_cached_after_waiter_timeout(self) -> None:
        """A slow-but-healthy connect must still be cached after waiters time out."""
        connect_started = asyncio.Event()
        allow_connect = asyncio.Event()
        client = MagicMock()

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            connect_started.set()
            await allow_connect.wait()
            return client

        with (
            patch(
                "syntara.core.temporal.client.Client.connect",
                new=_connect,
            ),
            patch("syntara.core.temporal.client.CONNECT_TIMEOUT_SECONDS", 0.05),
        ):
            try:
                assert await asyncio.wait_for(get_shared_client(), timeout=1.0) is None
                in_flight = client_mod._connect_task
                assert in_flight is not None
                assert not in_flight.cancelled()
                allow_connect.set()
                assert await asyncio.wait_for(in_flight, timeout=1.0) is client
                assert client_mod._cached_client is client
                assert await get_shared_client() is client
            finally:
                allow_connect.set()

    async def test_timed_out_connect_is_replaced(self) -> None:
        """A hung Client.connect older than the waiter budget is replaced on the next wait."""
        connect_calls = 0
        first_hang = asyncio.Event()
        second_client = MagicMock()

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            if connect_calls == 1:
                await first_hang.wait()
                return MagicMock()
            return second_client

        with (
            patch(
                "syntara.core.temporal.client.Client.connect",
                new=_connect,
            ),
            patch("syntara.core.temporal.client.CONNECT_TIMEOUT_SECONDS", 0.05),
        ):
            try:
                first = await asyncio.wait_for(get_shared_client(), timeout=1.0)
                assert first is None
                old_task = client_mod._connect_task
                assert old_task is not None
                assert not old_task.done()
                await asyncio.sleep(0.02)
                assert await get_shared_client() is second_client
                assert connect_calls == 2
                assert not old_task.cancelled()
            finally:
                first_hang.set()
                await asyncio.sleep(0)

    async def test_hung_connect_is_replaced_even_if_connect_ignores_cancel(self) -> None:
        """Replacement must not wait for Client.connect to honour cancellation."""
        connect_calls = 0
        first_hang = asyncio.Event()
        second_client = MagicMock()

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            if connect_calls == 1:
                try:
                    await first_hang.wait()
                except asyncio.CancelledError:
                    await first_hang.wait()
                return MagicMock()
            return second_client

        with (
            patch(
                "syntara.core.temporal.client.Client.connect",
                new=_connect,
            ),
            patch("syntara.core.temporal.client.CONNECT_TIMEOUT_SECONDS", 0.05),
        ):
            try:
                first = await asyncio.wait_for(get_shared_client(), timeout=1.0)
                assert first is None
                old_task = client_mod._connect_task
                assert old_task is not None
                await asyncio.sleep(0.02)
                assert await get_shared_client() is second_client
                assert connect_calls == 2
                assert client_mod._cached_client is second_client
                assert not old_task.cancelled()
            finally:
                first_hang.set()
                await asyncio.sleep(0)

    async def test_stale_connect_does_not_overwrite_newer_client(self) -> None:
        """A late success from a replaced connect must not replace the new client."""
        connect_calls = 0
        allow_first = asyncio.Event()
        first_client = MagicMock(name="stale")
        second_client = MagicMock(name="fresh")

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            if connect_calls == 1:
                try:
                    await allow_first.wait()
                except asyncio.CancelledError:
                    await allow_first.wait()
                return first_client
            return second_client

        with (
            patch(
                "syntara.core.temporal.client.Client.connect",
                new=_connect,
            ),
            patch("syntara.core.temporal.client.CONNECT_TIMEOUT_SECONDS", 0.05),
        ):
            try:
                assert await asyncio.wait_for(get_shared_client(), timeout=1.0) is None
                old_task = client_mod._connect_task
                assert old_task is not None
                await asyncio.sleep(0.02)
                assert await get_shared_client() is second_client
                assert not old_task.cancelled()
                allow_first.set()
                await asyncio.wait_for(old_task, timeout=1.0)
                assert client_mod._cached_client is second_client
            finally:
                allow_first.set()

    async def test_replaced_connect_kept_alive_against_gc(self) -> None:
        """A replaced connect must survive GC when only the module set holds it.

        Reproduces the drop-on-the-floor bug: after the first waiter times out,
        the replaced connect is referenced only by ``_pending_connect_tasks``.
        Unlike the sibling replacement tests, this one keeps no local strong
        ref to the old task, so ``gc.collect()`` would cancel it ("Task was
        destroyed but it is pending") without the strong-ref set.
        """
        connect_calls = 0
        allow_first = asyncio.Event()
        first_client = MagicMock(name="stale")
        second_client = MagicMock(name="fresh")

        async def _connect(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal connect_calls
            connect_calls += 1
            if connect_calls == 1:
                await allow_first.wait()
                return first_client
            return second_client

        with (
            patch(
                "syntara.core.temporal.client.Client.connect",
                new=_connect,
            ),
            patch("syntara.core.temporal.client.CONNECT_TIMEOUT_SECONDS", 0.05),
        ):
            try:
                # First waiter times out; the connect keeps running in the set.
                assert await asyncio.wait_for(get_shared_client(), timeout=1.0) is None
                stale_ref = weakref.ref(client_mod._connect_task)
                stale_task = stale_ref()
                assert stale_task is not None
                assert stale_task in client_mod._pending_connect_tasks

                # Replace the stale connect, then drop every local strong ref
                # to it. Only ``_pending_connect_tasks`` should hold it now.
                await asyncio.sleep(0.02)
                assert await get_shared_client() is second_client
                assert connect_calls == 2
                assert client_mod._connect_task is not stale_task
                del stale_task
                gc.collect()

                # Without the strong-ref set the task would be gone/cancelled.
                survivor = stale_ref()
                assert survivor is not None
                assert survivor in client_mod._pending_connect_tasks
                assert not survivor.cancelled()

                # A late success from the survivor still completes and, once
                # done, drops itself from the set via the done-callback.
                allow_first.set()
                assert await asyncio.wait_for(survivor, timeout=1.0) is not None
                await asyncio.sleep(0)
                assert survivor not in client_mod._pending_connect_tasks
                assert client_mod._cached_client is second_client
            finally:
                allow_first.set()


class TestInvalidateClient:
    """Tests for invalidate_client()."""

    async def test_invalidate_forces_reconnect(self) -> None:
        """After invalidation the next get_shared_client creates a new connection."""
        client_a = MagicMock()
        client_b = MagicMock()

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

    def test_invalidate_matching_client_clears_cache(self) -> None:
        """Invalidating the exact cached instance clears the cache."""
        cached = MagicMock()
        client_mod._cached_client = cached

        invalidate_client(cached)

        assert client_mod._cached_client is None

    def test_invalidate_foreign_client_leaves_cache(self) -> None:
        """Invalidating a client that is not the cached one must not evict it.

        An explicit-override connection, an injected test client, or a
        stale client another caller already replaced must never discard
        the healthy shared connection.
        """
        cached = MagicMock()
        foreign = MagicMock()
        client_mod._cached_client = cached

        invalidate_client(foreign)

        assert client_mod._cached_client is cached


class TestInvalidateOnConnectionError:
    """Tests for invalidate_on_connection_error()."""

    async def test_invalidates_on_unavailable(self) -> None:
        mock_client = MagicMock()
        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            await get_shared_client()

        assert client_mod._cached_client is not None
        invalidate_on_connection_error(RPCError("down", RPCStatusCode.UNAVAILABLE, b""))
        assert client_mod._cached_client is None

    async def test_invalidates_on_deadline_exceeded(self) -> None:
        mock_client = MagicMock()
        with patch(
            "syntara.core.temporal.client.Client.connect",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            await get_shared_client()

        assert client_mod._cached_client is not None
        invalidate_on_connection_error(RPCError("timeout", RPCStatusCode.DEADLINE_EXCEEDED, b""))
        assert client_mod._cached_client is None

    async def test_ignores_non_connection_rpc_error(self) -> None:
        mock_client = MagicMock()
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
        client_mod._cached_client = MagicMock()
        invalidate_on_connection_error(ValueError("something else"))
        assert client_mod._cached_client is not None

    def test_invalidates_only_the_matching_client(self) -> None:
        """A connection error from a foreign client must not evict the cached one."""
        cached = MagicMock()
        foreign = MagicMock()
        client_mod._cached_client = cached

        invalidate_on_connection_error(
            RPCError("down", RPCStatusCode.UNAVAILABLE, b""),
            client=foreign,
        )

        assert client_mod._cached_client is cached

    def test_invalidates_when_client_matches_cache(self) -> None:
        """A connection error from the cached client itself clears the cache."""
        cached = MagicMock()
        client_mod._cached_client = cached

        invalidate_on_connection_error(
            RPCError("down", RPCStatusCode.UNAVAILABLE, b""),
            client=cached,
        )

        assert client_mod._cached_client is None

    def test_foreign_client_with_non_connection_error_is_ignored(self) -> None:
        """Non-connection errors never invalidate, regardless of the client."""
        cached = MagicMock()
        foreign = MagicMock()
        client_mod._cached_client = cached

        invalidate_on_connection_error(
            RPCError("not found", RPCStatusCode.NOT_FOUND, b""),
            client=foreign,
        )

        assert client_mod._cached_client is cached
