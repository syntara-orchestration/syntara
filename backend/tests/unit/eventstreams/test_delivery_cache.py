"""Redis failure and stale references never replace authoritative terminal evidence."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from syntara.eventstreams.core.deduplication import DeliveryState, TerminalDelivery, TerminalReferenceCache
from syntara.eventstreams.services import delivery_cache
from syntara.eventstreams.services.delivery_cache import DeliveryRedisClient, EventDeliveryTerminalLookup
from tests.unit.eventstreams.test_delivery_identity import identity
from tests.unit.eventstreams.test_delivery_retention import session_factory


@pytest.mark.parametrize("cached", [None, "stale-digest", "{malformed", TimeoutError(), OSError()])
async def test_cache_content_or_failure_always_checks_postgresql(
    cached: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fake hit, corrupt entry, miss or outage cannot produce terminal evidence."""
    factory, _ = session_factory()
    cache = AsyncMock(spec=TerminalReferenceCache)
    if isinstance(cached, Exception):
        cache.get.side_effect = cached
    else:
        cache.get.return_value = cached
    repository = MagicMock()
    repository.lookup_terminal = AsyncMock(return_value=None)
    monkeypatch.setattr(delivery_cache, "EventDeliveryStore", MagicMock(return_value=repository))
    service = EventDeliveryTerminalLookup(factory, cache=cache)
    assert await service.lookup(identity()) is None
    repository.lookup_terminal.assert_awaited_once_with(identity())
    cache.put.assert_not_awaited()


@pytest.mark.parametrize("with_cache", [False, True])
async def test_terminal_lookup_works_without_redis_or_with_rejected_writes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    with_cache: bool,
) -> None:
    """Optional cache writes cannot undo committed database resolution."""
    factory, _ = session_factory()
    terminal = TerminalDelivery(identity=identity(), state=DeliveryState.REJECTED, resolved_at=datetime.now(UTC))
    repository = MagicMock()
    repository.lookup_terminal = AsyncMock(return_value=terminal)
    monkeypatch.setattr(delivery_cache, "EventDeliveryStore", MagicMock(return_value=repository))
    cache = AsyncMock(spec=TerminalReferenceCache)
    cache.put.side_effect = OSError()
    service = EventDeliveryTerminalLookup(factory, cache=cache if with_cache else None)
    assert await service.lookup(identity()) == terminal


async def test_terminal_reference_is_written_after_database_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """No claim, binding or uncommitted terminal state is placed in Redis."""
    factory, sessions = session_factory()
    terminal = TerminalDelivery(identity=identity(), state=DeliveryState.REJECTED, resolved_at=datetime.now(UTC))
    repository = MagicMock()
    repository.lookup_terminal = AsyncMock(return_value=terminal)
    monkeypatch.setattr(delivery_cache, "EventDeliveryStore", MagicMock(return_value=repository))
    cache = AsyncMock(spec=TerminalReferenceCache)

    async def write(_: object) -> None:
        sessions[0].begin.return_value.__aexit__.assert_awaited_once()
        sessions[0].__aexit__.assert_awaited_once()

    cache.put.side_effect = write
    assert await EventDeliveryTerminalLookup(factory, cache=cache).lookup(identity()) == terminal
    cache.put.assert_awaited_once_with(identity())


async def test_redis_value_contains_only_identity_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    """The concrete Redis client never stores event data or claim state."""
    client = DeliveryRedisClient()
    write = AsyncMock()
    monkeypatch.setattr(client, "cache_setex", write)
    await client.put(identity())
    write.assert_awaited_once_with(identity().cache_key, 60, identity().digest)
