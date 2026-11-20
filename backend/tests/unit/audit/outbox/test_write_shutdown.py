"""Insert-only audit shutdown never reads, exports or deletes shared rows."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from syntara.audit.outbox import worker as module
from syntara.audit.outbox.worker import AuditOutboxWorker
from tests.unit.audit.outbox.test_worker import _make_event


@pytest.mark.parametrize("blocked", [False, True])
async def test_write_only_shutdown_settles_local_inserts_without_publishing(monkeypatch, *, blocked: bool) -> None:
    factory = MagicMock(side_effect=AssertionError("Insert draining must not query the shared outbox"))
    worker = AuditOutboxWorker(name="write-only", interval_seconds=1, session_factory=factory, coordinate=False)
    publish = AsyncMock(side_effect=AssertionError("The producer process must never publish shared audit rows"))
    monkeypatch.setattr(module, "publish_outbox_events", publish)
    finished = asyncio.Event()

    async def insert(_event: object) -> None:
        try:
            if blocked:
                await asyncio.Event().wait()
        finally:
            finished.set()

    monkeypatch.setattr(worker, "_write", insert)
    worker.write_to_outbox(_make_event())
    async with asyncio.timeout(1):
        await worker.drain_writes(timeout_seconds=0.02)
    assert finished.is_set()
    assert not worker._pending
    assert worker._task is None
    factory.assert_not_called()
    publish.assert_not_awaited()
