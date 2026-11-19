"""Cancellation reconciliation retries from existing state without an outbox."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4, uuid5

import pytest

from syntara.execution_plane.reconciliation import reconcile_work_item_cancellations


@pytest.mark.asyncio
async def test_reconciliation_pages_and_continues_after_a_failed_cancel():
    execution_id = uuid4()
    ids = [uuid5(execution_id, name) for name in ("first", "second", "third")]
    client = AsyncMock()
    client.list_work_items.side_effect = [
        {"resources": [{"id": str(item)} for item in ids[:2]], "next": "page-two"},
        {"resources": [{"id": str(ids[2])}], "next": None},
    ]
    client.cancel_work_item.side_effect = [RuntimeError("EP unavailable"), None, None]
    session = AsyncMock()
    session.exec.side_effect = [
        Mock(all=lambda: [(ids[0], execution_id, "first"), (ids[1], execution_id, "second")]),
        Mock(all=lambda: [(ids[2], execution_id, "third")]),
    ]

    assert await reconcile_work_item_cancellations(session, client) == 2
    assert [call.kwargs["work_item_id"] for call in client.cancel_work_item.await_args_list] == ids
    calls = client.list_work_items.await_args_list
    assert [call.kwargs["cursor"] for call in calls] == [None, "page-two"]
    assert calls[0].kwargs["filters"] == calls[1].kwargs["filters"]
    session.commit.assert_not_awaited()
    client.delete_work_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_cancellation_can_be_retried_in_a_later_pass():
    execution_id = uuid4()
    item_id = uuid5(execution_id, "script")
    session = AsyncMock()
    session.exec.return_value = Mock(all=lambda: [(item_id, execution_id, "script")])
    client = AsyncMock()
    client.list_work_items.return_value = {"resources": [{"id": str(item_id)}], "next": None}
    client.cancel_work_item.side_effect = [RuntimeError("offline"), None]

    assert await reconcile_work_item_cancellations(session, client) == 0
    assert await reconcile_work_item_cancellations(session, client) == 1
    assert client.cancel_work_item.await_count == 2


@pytest.mark.asyncio
async def test_missing_ownership_is_ignored_without_deleting_work():
    client = AsyncMock()
    client.list_work_items.return_value = {"resources": [{"id": str(uuid4())}], "next": None}
    session = AsyncMock()
    session.exec.return_value = Mock(all=list)

    assert await reconcile_work_item_cancellations(session, client) == 0
    client.cancel_work_item.assert_not_awaited()
    client.delete_work_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_unrelated_activity_identity_is_not_cancelled():
    execution_id, item_id = uuid4(), uuid4()
    session = AsyncMock()
    session.exec.return_value = Mock(all=lambda: [(item_id, execution_id, "script")])
    client = AsyncMock()
    client.list_work_items.return_value = {"resources": [{"id": str(item_id)}], "next": None}

    assert await reconcile_work_item_cancellations(session, client) == 0
    client.cancel_work_item.assert_not_awaited()


def test_periodic_cancellation_defaults_and_configuration(monkeypatch):
    from syntara.core.config.base import get_settings
    from syntara.execution_plane.reconciliation import get_cancellation_reconciliation_worker

    monkeypatch.delenv("APP_EP_CANCELLATION_RECONCILIATION_INTERVAL_SECONDS", raising=False)
    get_settings.cache_clear()
    try:
        worker = get_cancellation_reconciliation_worker()
        assert worker._interval_seconds == 1800
        assert worker._coordinate is True
        monkeypatch.setenv("APP_EP_CANCELLATION_RECONCILIATION_INTERVAL_SECONDS", "3600")
        get_settings.cache_clear()
        assert get_cancellation_reconciliation_worker()._interval_seconds == 3600
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_periodic_callback_closes_session_and_client_on_failure(monkeypatch):
    from syntara.execution_plane import reconciliation

    session_context, client_context = AsyncMock(), AsyncMock()
    session_factory = Mock(return_value=session_context)
    monkeypatch.setattr(reconciliation, "ExecutionPlaneHttpClient", lambda: client_context)
    reconcile = AsyncMock(side_effect=RuntimeError("EP unavailable"))
    monkeypatch.setattr(reconciliation, "reconcile_work_item_cancellations", reconcile)

    with pytest.raises(RuntimeError, match="EP unavailable"):
        await reconciliation._reconcile_cancellations(session_factory)

    reconcile.assert_awaited_once_with(session_context.__aenter__.return_value, client_context.__aenter__.return_value)
    session_context.__aexit__.assert_awaited_once()
    client_context.__aexit__.assert_awaited_once()
