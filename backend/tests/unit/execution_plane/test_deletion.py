"""Deletion cleanup is backgrounded, isolated per item, and best effort."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from syntara.execution_plane import deletion


@pytest.mark.asyncio
async def test_delete_continues_after_an_ep_failure(monkeypatch):
    ids = [uuid4(), uuid4()]
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.delete_work_item.side_effect = [RuntimeError("EP unavailable"), None]
    monkeypatch.setattr(deletion, "ExecutionPlaneHttpClient", lambda: client)

    await deletion.delete_execution_plane_work_items(ids)

    assert [call.kwargs["work_item_id"] for call in client.delete_work_item.await_args_list] == ids


@pytest.mark.asyncio
async def test_scheduled_deletion_does_not_block_the_caller(monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()
    ids = [uuid4()]

    async def blocked_cleanup(work_item_ids) -> None:
        assert work_item_ids == ids
        started.set()
        await release.wait()

    monkeypatch.setattr(deletion, "delete_execution_plane_work_items", blocked_cleanup)
    deletion.schedule_work_item_deletion(ids)
    tasks = tuple(deletion._pending_deletions)
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert all(not task.done() for task in tasks)
    finally:
        release.set()
        await asyncio.gather(*tasks)
        await asyncio.sleep(0)
    assert not deletion._pending_deletions


@pytest.mark.asyncio
async def test_scheduled_client_setup_failure_is_observed(monkeypatch):
    cleanup = AsyncMock(side_effect=RuntimeError("EP is not configured"))
    monkeypatch.setattr(deletion, "delete_execution_plane_work_items", cleanup)
    deletion.schedule_work_item_deletion([uuid4()])
    await asyncio.gather(*tuple(deletion._pending_deletions), return_exceptions=True)
    await asyncio.sleep(0)
    assert not deletion._pending_deletions
