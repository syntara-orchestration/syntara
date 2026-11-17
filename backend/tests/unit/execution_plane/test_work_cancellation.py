"""Bulk cancellation preserves dispatch identity and bounds explicit ID batches."""

from unittest.mock import AsyncMock
from uuid import uuid4, uuid5

import pytest

from syntara.execution_plane import cancellation


@pytest.mark.asyncio
async def test_ten_activity_cancellations_use_one_request(monkeypatch):
    execution_id = uuid4()
    client = AsyncMock()
    client.__aenter__.return_value = client
    monkeypatch.setattr(cancellation, "ExecutionPlaneHttpClient", lambda: client)
    names = [str(i) for i in range(10)]
    accepted = await cancellation.cancel_execution_plane_work_items(execution_id, names)
    assert accepted == [uuid5(execution_id, name) for name in names]
    client.cancel_work_items.assert_awaited_once()
    assert client.cancel_work_items.call_args.kwargs["selector"].work_item_ids == accepted


@pytest.mark.asyncio
async def test_failed_batch_does_not_prevent_next_batch(monkeypatch):
    execution_id = uuid4()
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.cancel_work_items.side_effect = [RuntimeError("offline"), None]
    monkeypatch.setattr(cancellation, "ExecutionPlaneHttpClient", lambda: client)
    accepted = await cancellation.cancel_execution_plane_work_items(execution_id, [str(i) for i in range(101)])
    assert accepted == [uuid5(execution_id, "100")]
    assert [len(c.kwargs["selector"].work_item_ids) for c in client.cancel_work_items.await_args_list] == [100, 1]


@pytest.mark.asyncio
async def test_execution_cancellation_uses_filter_without_activity_lookup(monkeypatch):
    execution_id = uuid4()
    client = AsyncMock()
    client.__aenter__.return_value = client
    monkeypatch.setattr(cancellation, "ExecutionPlaneHttpClient", lambda: client)
    await cancellation.cancel_execution_plane_work_for_execution(execution_id)
    client.cancel_work_items.assert_awaited_once()
    assert client.cancel_work_items.call_args.kwargs["selector"].model_dump(exclude_none=True) == {
        "runtime_context": {"execution_id": str(execution_id)}
    }
