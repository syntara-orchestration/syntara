"""Retained outputs survive retry chains without duplicate activity records."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.services.retry_activity_sync import sync_restored_activities


def row(name: str, status: ActivityStatus = ActivityStatus.COMPLETED) -> ActivityExecution:
    """Build a persisted activity-shaped row."""
    return ActivityExecution(
        execution_id=uuid4(),
        activity_name=name,
        node_type=NodeType.SCRIPT,
        temporal_activity_id=name,
        status=status,
        output_data={"receipt": "source"},
        iteration=1 if "#iter-" in name else 0,
    )


def session_for(sources: list[ActivityExecution], targets: list[ActivityExecution]) -> AsyncMock:
    """Provide query results without replacing persistence logic."""
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = MagicMock(retried_from_execution_id=uuid4())
    session.exec.side_effect = [MagicMock(all=lambda: sources), MagicMock(all=lambda: targets)]
    return session


@pytest.mark.asyncio
async def test_restore_pending_and_create_iteration_then_resync_is_idempotent() -> None:
    """Copy source outputs, but preserve the retry's own input-display contract."""
    source = row("body")
    iteration = row("body#iter-1")
    target = row("body", ActivityStatus.PENDING)
    target.output_data = None
    target.input_data = {"current": "input"}
    session = session_for([source, iteration], [target])
    updated, created = await sync_restored_activities(session, target.execution_id, ["body", "body#iter-1"])
    assert [item[0] for item in updated] == [target]
    assert len(created) == 1
    assert target.status == ActivityStatus.COMPLETED
    assert target.output_data == source.output_data
    assert target.input_data == {"current": "input"}
    assert created[0].iteration == 1
    assert created[0].output_data == iteration.output_data
    session.commit.assert_not_awaited()

    session = session_for([source, iteration], [target, *created])
    assert await sync_restored_activities(session, target.execution_id, ["body", "body#iter-1"]) == ([], [])
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_retry_chain_can_reuse_an_already_restored_source() -> None:
    """A restored row can become the source for a subsequent retry."""
    source = row("upstream")
    session = session_for([source], [])
    _, first_retry = await sync_restored_activities(session, uuid4(), ["upstream"])
    session = session_for(first_retry, [])
    _, next_retry = await sync_restored_activities(session, uuid4(), ["upstream"])
    assert next_retry[0].status == ActivityStatus.COMPLETED
    assert next_retry[0].output_data == {"receipt": "source"}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [ActivityStatus.RUNNING, ActivityStatus.FAILED, ActivityStatus.COMPLETED])
async def test_restore_never_overwrites_a_dispatched_node(status: ActivityStatus) -> None:
    """A delayed sync cannot replace fresh execution results with old output."""
    target = row("node", status)
    target.output_data = {"receipt": "fresh"}
    session = session_for([row("node")], [target])
    assert await sync_restored_activities(session, target.execution_id, ["node"]) == ([], [])
    assert target.output_data == {"receipt": "fresh"}


@pytest.mark.asyncio
async def test_normal_execution_does_not_query_source_outputs() -> None:
    """Restoration is constrained to linked retry executions."""
    session = session_for([], [])
    session.get.return_value.retried_from_execution_id = None
    assert await sync_restored_activities(session, uuid4(), ["node"]) == ([], [])
    session.exec.assert_not_awaited()


@pytest.mark.asyncio
async def test_monitor_seeds_iteration_counters_before_resumed_scheduling() -> None:
    """A resumed body gets the next suffix instead of overwriting iteration zero."""
    from unittest.mock import patch

    from syntara.workflows.workflow_engine.services.activity_sync_service import (
        ActivitySyncService,
        ExecutionMonitorMetadata,
    )

    target = row("body")
    retained_iteration = row("body#iter-1")
    session = AsyncMock(spec=AsyncSession)
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    service = ActivitySyncService(MagicMock(), factory)
    metadata = ExecutionMonitorMetadata(
        execution_id=target.execution_id,
        last_processed_event_id=0,
        activity_definitions_map={"body": {"type": "script"}},
        activity_index_map={"body": 0},
        pending_activity_updates={},
        next_activity_index=1,
        is_retry=True,
    )
    handle = AsyncMock()
    handle.query.return_value = ["body", "body#iter-1"]
    with (
        patch(
            "syntara.workflows.workflow_engine.services.activity_node_sync.sync_restored_activities",
            new=AsyncMock(return_value=([(target, {})], [retained_iteration])),
        ),
        patch.object(service, "_publish_activity_patches", new_callable=AsyncMock) as publish,
    ):
        await service._sync_restored_retry_nodes(metadata, handle)
        publish.assert_awaited_once()
        session.commit.assert_awaited_once()
    assert metadata.iteration_counters == {"body": 1}
    assert metadata.activity_index_map["body#iter-1"] == 1
    assert "body" in metadata.terminal_activity_ids
    scheduled = MagicMock(event_id=42)
    scheduled.activity_task_scheduled_event_attributes.activity_id = "body"
    scheduled.activity_task_scheduled_event_attributes.start_to_close_timeout = None
    service._process_activity_scheduled(scheduled, metadata)
    assert metadata.pending_activity_updates[42]["_is_loop_iteration"] is True
    new_row, created = service._get_or_create_iteration_record(
        "body",
        {"body": target, "body#iter-1": retained_iteration},
        metadata,
        session,
    )
    assert created
    assert new_row is not None
    assert new_row.activity_name == "body#iter-2"
