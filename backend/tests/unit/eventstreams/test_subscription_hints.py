"""Disposable Redis hints, unavailable Redis, and listener cleanup."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import RedisError

from syntara.core.constants import EventWorkerDefaults
from syntara.eventstreams.services.subscription_hints import SubscriptionHintListener
from syntara.eventstreams.services.worker_redis import EventWorkerRedisClient
from tests.unit.eventstreams.test_consumer_service import eventually


async def test_hint_wakes_authoritative_reconciliation_and_closes_resources():
    request = MagicMock()
    client, pubsub = MagicMock(), MagicMock()
    wait = asyncio.Event()
    calls = 0

    async def message(**_kwargs: object) -> dict[str, str] | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"type": "message", "data": "untrusted configuration is ignored"}
        await wait.wait()
        return None

    pubsub.get_message = AsyncMock(side_effect=message)
    pubsub.aclose = AsyncMock()
    client.pubsub_subscribe = AsyncMock(return_value=pubsub)
    client.disconnect = AsyncMock()
    listener = SubscriptionHintListener(request, client)
    listener.start()
    listener.start()
    await eventually(lambda: request.call_count == 1)
    await listener.stop()
    request.assert_called_once_with()
    client.pubsub_subscribe.assert_awaited_once_with(EventWorkerDefaults.HINT_CHANNEL)
    pubsub.aclose.assert_awaited_once()
    client.disconnect.assert_not_awaited()


async def test_unavailable_redis_does_not_raise_into_worker():
    request, client = MagicMock(), MagicMock()
    client.pubsub_subscribe = AsyncMock(side_effect=OSError("Redis unavailable"))
    client.disconnect = AsyncMock()
    listener = SubscriptionHintListener(request, client)
    listener.start()
    await eventually(lambda: client.pubsub_subscribe.await_count == 1)
    await listener.stop()
    request.assert_not_called()
    client.disconnect.assert_not_awaited()


async def test_pubsub_retry_keeps_shared_cache_pool_available(monkeypatch):
    monkeypatch.setattr(EventWorkerDefaults, "RECONCILE_INTERVAL_SECONDS", 0.01)
    client = EventWorkerRedisClient()
    backend = MagicMock()
    backend.getrange = AsyncMock(return_value="isolated terminal proof")
    backend.aclose = AsyncMock()
    first, second = MagicMock(), MagicMock()
    for subscription in (first, second):
        subscription.subscribe = AsyncMock()
        subscription.aclose = AsyncMock()
    first.get_message = AsyncMock(side_effect=OSError("isolated dropped subscription"))

    async def wait(**_kwargs: object) -> None:
        await asyncio.Event().wait()

    second.get_message = AsyncMock(side_effect=wait)
    backend.pubsub.side_effect = [first, second]
    client._client = backend
    listener = SubscriptionHintListener(MagicMock(), client)
    listener.start()
    try:
        await eventually(lambda: second.get_message.await_count > 0)
        first.aclose.assert_awaited_once()
        assert await client.get("isolated-proof-key") == "isolated terminal proof"
        backend.aclose.assert_not_awaited()
    finally:
        await listener.stop()
    second.aclose.assert_awaited_once()
    backend.aclose.assert_not_awaited()
    await client.disconnect()
    backend.aclose.assert_awaited_once()


async def test_partial_subscription_failure_closes_subscription_without_pool_disconnect():
    client = EventWorkerRedisClient()
    backend, pubsub = MagicMock(), MagicMock()
    backend.pubsub.return_value = pubsub
    backend.aclose = AsyncMock()
    pubsub.subscribe = AsyncMock(side_effect=OSError("isolated subscribe failure"))
    pubsub.aclose = AsyncMock()
    client._client = backend
    with pytest.raises(RedisError):
        await client.pubsub_subscribe(EventWorkerDefaults.HINT_CHANNEL)
    pubsub.aclose.assert_awaited_once()
    backend.aclose.assert_not_awaited()
    await client.disconnect()
