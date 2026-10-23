"""Disposable Redis hints, unavailable Redis, and listener cleanup."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from syntara.core.constants import EventWorkerDefaults
from syntara.eventstreams.services.subscription_hints import SubscriptionHintListener
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
    client.disconnect.assert_awaited_once()


async def test_unavailable_redis_does_not_raise_into_worker():
    request, client = MagicMock(), MagicMock()
    client.pubsub_subscribe = AsyncMock(side_effect=OSError("Redis unavailable"))
    client.disconnect = AsyncMock()
    listener = SubscriptionHintListener(request, client)
    listener.start()
    await eventually(lambda: client.disconnect.await_count == 1)
    await listener.stop()
    request.assert_not_called()
