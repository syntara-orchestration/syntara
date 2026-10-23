"""Shared activity identity with real PostgreSQL and independently started paths.

The monitor alone creates AO rows. Temporal metadata, EP HTTP, and Temporal
completion are doubles; row creation and callback lookups use PostgreSQL.
"""

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid5

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.execution_plane.commands.completion import CompletionCommandHandler
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution
from syntara.workflows.workflow_engine.activities.ep import ep_dispatch_activity as dispatch
from syntara.workflows.workflow_engine.services.activity_sync_service import ActivitySyncService

_NODE_ID = "test_activity"
_DEFINITIONS = {
    _NODE_ID: {"type": "script"},
    "other_activity": {"type": "http_request"},
}


@pytest.fixture
def ep_submission(test_execution: Execution) -> Generator[AsyncMock, None, None]:
    """Accept EP work without creating its AO activity row."""
    info = Mock(
        workflow_id=test_execution.temporal_workflow_id,
        workflow_run_id="test-run",
        activity_id=_NODE_ID,
    )
    with (
        patch.object(dispatch.activity, "info", return_value=info),
        patch.object(dispatch, "ExecutionPlaneHttpClient"),
        patch.object(dispatch, "_submit_and_read_work", return_value={"status": "pending"}) as submission,
    ):
        yield submission


@pytest.mark.asyncio
@pytest.mark.parametrize("monitor_first", [False, True])
async def test_monitor_and_dispatch_share_identity_in_either_order(
    test_execution: Execution,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    ep_submission: AsyncMock,
    *,
    monitor_first: bool,
) -> None:
    """An early callback can retry after the monitor creates the matching row."""
    monitor = ActivitySyncService(Mock(), test_db_session_factory, AsyncMock())
    if monitor_first:
        await monitor._create_all_activities_upfront(test_execution.id, _DEFINITIONS)

    assert (
        await dispatch._dispatch_to_ep({"language": "bash", "code": "echo ok"}, None, test_execution.id, None) is None
    )
    work_id = ep_submission.call_args.args[1].command_id
    assert work_id == uuid5(test_execution.id, _NODE_ID)

    temporal = AsyncMock()
    result = {"output": {"stdout": "ok"}}
    async with test_db_session_factory() as reader:
        if not monitor_first:
            assert (
                await reader.exec(select(ActivityExecution).where(ActivityExecution.execution_id == test_execution.id))
            ).all() == []
        assert (
            await CompletionCommandHandler()._complete_activity(
                context=AOCommandContext(reader, temporal), work_id=work_id, status="completed", result=result
            )
            is monitor_first
        )
    if not monitor_first:
        temporal.complete_async_activity.assert_not_awaited()

    await monitor._create_all_activities_upfront(test_execution.id, _DEFINITIONS)
    async with test_db_session_factory() as reader:
        assert (
            await CompletionCommandHandler()._complete_activity(
                context=AOCommandContext(reader, temporal), work_id=work_id, status="completed", result=result
            )
            is True
        )
        rows = (
            await reader.exec(select(ActivityExecution).where(ActivityExecution.execution_id == test_execution.id))
        ).all()
        assert {row.activity_name for row in rows} == set(_DEFINITIONS)
        assert all(row.id == uuid5(test_execution.id, row.temporal_activity_id) for row in rows)
        assert next(row.id for row in rows if row.activity_name == _NODE_ID) == work_id
    temporal.complete_async_activity.assert_awaited_with(
        temporal_workflow_id=test_execution.temporal_workflow_id, activity_id=_NODE_ID, result=result
    )


@pytest.mark.asyncio
async def test_monitor_updates_row_created_after_dispatch(
    test_execution: Execution,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    ep_submission: AsyncMock,
) -> None:
    await dispatch._dispatch_to_ep({"language": "bash", "code": "echo ok"}, None, test_execution.id, None)
    work_id = ep_submission.call_args.args[1].command_id
    monitor = ActivitySyncService(Mock(), test_db_session_factory, AsyncMock())
    metadata = await monitor._initialize_monitoring(test_execution.id)
    now = datetime.now(UTC)
    metadata.pending_activity_updates[1] = {
        "activity_id": _NODE_ID,
        "status": ActivityStatus.COMPLETED,
        "started_at": now,
        "completed_at": now,
        "retry_count": 0,
        "error_details": None,
    }
    metadata.pending_sync_event_ids.add(1)
    handle = Mock()
    handle.query = AsyncMock(side_effect=[{"language": "bash", "code": "echo ok"}, {"output": {"stdout": "ok"}}])

    await monitor._sync_activities_to_db(metadata, handle)

    async with test_db_session_factory() as reader:
        row = await reader.get(ActivityExecution, work_id)
        assert row is not None
        assert row.status == ActivityStatus.COMPLETED
        assert row.output_data == {"output": {"stdout": "ok"}}
