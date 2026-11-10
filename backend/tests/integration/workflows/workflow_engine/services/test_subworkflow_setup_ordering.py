"""Deterministic for_each sub-workflow aggregate row under event-ordered sync (DB-backed).

Every for_each iteration of a sub-workflow node maps to the same aggregate
ActivityExecution row. The synchronizer applies pending updates in ascending Temporal
event-id order, so the row's final input_data/output_data (and the emitted WebSocket
state) is deterministic: the iteration with the highest scheduled event id wins, regardless of the
underlying set's iteration order.

These drive the real event processor + synchronizer against the alembic-built schema.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlmodel import select
from temporalio.api.enums.v1 import EventType

from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.services.activity_sync_service import ActivitySyncService
from syntara.workflows.workflow_engine.services.activity_sync_types import ExecutionMonitorMetadata

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

_PREFIX = "__internal__setup_sub_workflow_"
_NODE = "sub_wf_node"
_EMPTY_DEF: dict[str, Any] = {"schema_version": "2.0.0", "triggers": [], "nodes": [], "edges": []}


def _setup_result(child_workflow_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "execution_id": f"child-exec-{child_workflow_id}",
        "child_workflow_id": child_workflow_id,
        "child_workflow_name": f"child-{child_workflow_id}",
        "child_workflow_version": 1,
        "trigger_node_id": "child_trigger",
        "input_data": input_data,
        "workflow_definition": {"nodes": []},
        "task_queue": "tq",
    }


def _scheduled(event_id: int, activity_id: str) -> Mock:
    event = Mock()
    event.event_type = EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
    event.event_id = event_id
    event.event_time = datetime.now(UTC)
    attrs = Mock()
    attrs.activity_id = activity_id
    attrs.start_to_close_timeout = None
    event.activity_task_scheduled_event_attributes = attrs
    return event


def _started(event_id: int, scheduled_event_id: int) -> Mock:
    event = Mock()
    event.event_type = EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED
    event.event_id = event_id
    event.event_time = datetime.now(UTC)
    attrs = Mock()
    attrs.scheduled_event_id = scheduled_event_id
    attrs.attempt = 1
    attrs.last_failure = None
    event.activity_task_started_event_attributes = attrs
    return event


def _completed(event_id: int, scheduled_event_id: int, result: dict[str, Any]) -> Mock:
    event = Mock()
    event.event_type = EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED
    event.event_id = event_id
    event.event_time = datetime.now(UTC)
    attrs = Mock()
    attrs.scheduled_event_id = scheduled_event_id
    payload = Mock()
    payload.data = json.dumps(result).encode()
    attrs.result = Mock(payloads=[payload])
    event.activity_task_completed_event_attributes = attrs
    return event


async def _seed_parent_with_node_row(session: AsyncSession, *, created_by: UUID, project_id: UUID) -> UUID:
    """Create a parent Execution + the aggregate sub_workflow node row; return execution id."""
    wf_id = uuid4()
    session.add(Workflow(id=wf_id, name=f"parent-{wf_id.hex[:8]}", created_by=created_by, project_id=project_id))
    await session.flush()
    ver_id = uuid4()
    session.add(
        WorkflowVersion(
            id=ver_id,
            workflow_id=wf_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_EMPTY_DEF,
            created_by=created_by,
        )
    )
    await session.flush()
    exec_id = uuid4()
    session.add(
        Execution(
            id=exec_id,
            workflow_id=wf_id,
            workflow_version_id=ver_id,
            temporal_workflow_id=f"tmp-{exec_id.hex[:8]}",
            created_by=created_by,
            updated_by=created_by,
            project_id=project_id,
        )
    )
    await session.flush()
    session.add(
        ActivityExecution(
            execution_id=exec_id,
            activity_name=_NODE,
            node_type="sub_workflow",
            temporal_activity_id=_NODE,
            status=ActivityStatus.RUNNING,
        )
    )
    await session.commit()
    return exec_id


def _metadata(exec_id: UUID) -> ExecutionMonitorMetadata:
    return ExecutionMonitorMetadata(
        execution_id=exec_id,
        last_processed_event_id=0,
        activity_definitions_map={},
        activity_index_map={},
        pending_activity_updates={},
    )


def _drive_iteration(
    service: ActivitySyncService, metadata: ExecutionMonitorMetadata, *, sched: int, iter_idx: int, child_wf: str
) -> None:
    """Feed SCHEDULED/STARTED/COMPLETED for one for_each iteration through the real processor."""
    activity_id = f"{_PREFIX}{_NODE}_iter_{iter_idx}"
    service._process_activity_scheduled(_scheduled(sched, activity_id), metadata)
    service._process_activity_started(_started(sched + 1000, sched), metadata)
    service._process_activity_completed(
        _completed(sched + 2000, sched, _setup_result(child_wf, {"iter": iter_idx})), metadata
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_for_each_aggregate_row_is_deterministic_latest_wins(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """The aggregate row reflects the highest-event-id iteration, not set order."""
    exec_id = await _seed_parent_with_node_row(test_db_session, created_by=test_user.id, project_id=test_project_id)
    publisher = AsyncMock()
    service = ActivitySyncService(Mock(), test_db_session_factory, publisher)
    metadata = _metadata(exec_id)

    # Scheduled ids chosen so raw set order ([16, 1, 2]) differs from sorted ([1, 2, 16]).
    assert list({16, 1, 2}) != sorted({16, 1, 2})
    _drive_iteration(service, metadata, sched=16, iter_idx=0, child_wf="wf-HIGH")
    _drive_iteration(service, metadata, sched=1, iter_idx=1, child_wf="wf-low")
    _drive_iteration(service, metadata, sched=2, iter_idx=2, child_wf="wf-mid")

    await service._sync_activities_to_db(metadata, Mock())

    async with test_db_session_factory() as session:
        result = await session.exec(select(ActivityExecution).where(ActivityExecution.execution_id == exec_id))
        rows = result.all()
    assert len(rows) == 1  # single aggregate row, not one-per-iteration
    row = rows[0]
    assert row.input_data is not None
    assert row.output_data is not None
    # Highest scheduled id (16) wins deterministically.
    assert row.input_data["workflow_id"] == "wf-HIGH"
    assert row.input_data["input_parameters"] == {"iter": 0}
    assert row.output_data["workflow_id"] == "wf-HIGH"
    # WebSocket state derives from this persisted aggregate row (asserted above),
    # so it reflects the winning wf-HIGH iteration. The publish path itself is not
    # exercised by driving _sync_activities_to_db directly (it runs in the monitor
    # flow), so determinism is asserted on the row rather than the publisher here.


@pytest.mark.integration
@pytest.mark.asyncio
async def test_for_each_aggregate_row_deterministic_across_batches(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """A later batch (higher scheduled ids) overwrites an earlier one.

    Manually invokes synchronization twice: this validates cross-batch update
    behaviour, not the monitor's checkpoint guarantee. Batch monotonicity itself is
    enforced by the monitor's ``last_processed_event_id`` skip and is not exercised here.
    """
    exec_id = await _seed_parent_with_node_row(test_db_session, created_by=test_user.id, project_id=test_project_id)
    service = ActivitySyncService(Mock(), test_db_session_factory, AsyncMock())
    metadata = _metadata(exec_id)

    # Batch 1: lower scheduled ids.
    _drive_iteration(service, metadata, sched=10, iter_idx=0, child_wf="wf-batch1-a")
    _drive_iteration(service, metadata, sched=20, iter_idx=1, child_wf="wf-batch1-b")
    await service._sync_activities_to_db(metadata, Mock())  # clears pending

    # Batch 2: strictly higher scheduled ids (monotonic forward progress).
    # Highest scheduled id across both batches is 130 -> wf-batch2-a is the winner.
    _drive_iteration(service, metadata, sched=130, iter_idx=2, child_wf="wf-batch2-a")
    _drive_iteration(service, metadata, sched=120, iter_idx=3, child_wf="wf-batch2-b")
    await service._sync_activities_to_db(metadata, Mock())

    async with test_db_session_factory() as session:
        result = await session.exec(select(ActivityExecution).where(ActivityExecution.execution_id == exec_id))
        rows = result.all()
    assert len(rows) == 1
    # Highest id overall is 130 (batch 2) -> wf-batch2-a wins.
    assert rows[0].input_data["workflow_id"] == "wf-batch2-a"
