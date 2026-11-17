"""Deletion cleanup queries EP by owner, runs in the background, and is best effort."""

import asyncio
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from syntara.execution_plane import deletion


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_field", ["project_id", "workflow_id"])
async def test_delete_pages_by_owner_and_continues_after_an_ep_failure(monkeypatch, owner_field):
    owner_id = uuid4()
    ids = [uuid4(), uuid4(), uuid4()]
    client: AsyncMock = AsyncMock()
    client.__aenter__.return_value = client
    client.list_work_items.side_effect = [
        {"resources": [{"id": str(item)} for item in ids[:2]], "next": "page-two"},
        {"resources": [{"id": str(ids[2])}], "next": None},
    ]
    client.delete_work_item.side_effect = [RuntimeError("EP unavailable"), None, None]
    monkeypatch.setattr(deletion, "ExecutionPlaneHttpClient", lambda: client)

    await deletion.delete_execution_plane_work_items(owner_field=owner_field, owner_id=owner_id)

    assert [call.kwargs["work_item_id"] for call in client.delete_work_item.await_args_list] == ids
    assert [call.kwargs for call in client.list_work_items.await_args_list] == [
        {"limit": 100, "cursor": cursor, "sort": "id", "filters": {f"runtime_context[{owner_field}]": str(owner_id)}}
        for cursor in (None, "page-two")
    ]


@pytest.mark.asyncio
async def test_owner_with_no_ep_work_sends_no_deletion_requests(monkeypatch):
    client: AsyncMock = AsyncMock()
    client.__aenter__.return_value = client
    client.list_work_items.return_value = {"resources": [], "next": None}
    monkeypatch.setattr(deletion, "ExecutionPlaneHttpClient", lambda: client)

    await deletion.delete_execution_plane_work_items(owner_field="workflow_id", owner_id=uuid4())

    client.delete_work_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_repeated_cursor_stops_cleanup(monkeypatch):
    client: AsyncMock = AsyncMock()
    client.__aenter__.return_value = client
    client.list_work_items.return_value = {"resources": [], "next": "same-page"}
    monkeypatch.setattr(deletion, "ExecutionPlaneHttpClient", lambda: client)

    with pytest.raises(ValueError, match="repeated work-item cursor"):
        await deletion.delete_execution_plane_work_items(owner_field="project_id", owner_id=uuid4())

    assert client.list_work_items.await_count == 2


@pytest.mark.asyncio
async def test_scheduled_deletion_does_not_block_the_caller(monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()
    project_id = uuid4()

    async def blocked_cleanup(*, owner_field, owner_id) -> None:
        assert owner_field == "project_id"
        assert owner_id == project_id
        started.set()
        await release.wait()

    monkeypatch.setattr(deletion, "delete_execution_plane_work_items", blocked_cleanup)
    deletion.schedule_work_item_deletion(owner_field="project_id", owner_id=project_id)
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
@pytest.mark.parametrize("failure_stage", ["setup", "list"])
async def test_scheduled_ep_failure_is_observed(monkeypatch, failure_stage):
    client: AsyncMock = AsyncMock()
    client.__aenter__.return_value = client
    client.list_work_items.side_effect = RuntimeError("EP unavailable")

    def factory() -> AsyncMock:
        if failure_stage == "setup":
            msg = "EP is not configured"
            raise RuntimeError(msg)
        return client

    monkeypatch.setattr(deletion, "ExecutionPlaneHttpClient", factory)
    logger = Mock()
    monkeypatch.setattr(deletion, "logger", logger)

    deletion.schedule_work_item_deletion(owner_field="workflow_id", owner_id=uuid4())
    await asyncio.gather(*tuple(deletion._pending_deletions), return_exceptions=True)
    await asyncio.sleep(0)

    assert not deletion._pending_deletions
    logger.error.assert_called_once_with("Execution Plane deletion task failed", error_type="RuntimeError")
