"""Prepared event missing-run handling belongs to durable delivery recovery."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SATimeoutError
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.service import RPCError, RPCStatusCode

from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.workflow_engine.services import activity_sync_monitor as module
from syntara.workflows.workflow_engine.services.activity_sync_monitor import ActivitySyncMonitorMixin


def monitor(execution: Execution | None) -> tuple[ActivitySyncMonitorMixin, MagicMock]:
    """Exercise the real monitor boundary with no Temporal or database I/O."""
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    session.get = AsyncMock(return_value=execution)
    instance = ActivitySyncMonitorMixin()
    instance.session_factory = lambda: session
    return instance, session


def execution(status: ExecutionStatus = ExecutionStatus.PENDING, *, prepared: bool = True) -> Execution:
    return Execution(
        workflow_id=UUID(int=1),
        workflow_version_id=UUID(int=2),
        project_id=UUID(int=3),
        created_by=UUID(int=4),
        temporal_workflow_id="event-v1-test",
        status=status,
        execution_metadata={"event_delivery": {"scheduling_state": "prepared"}} if prepared else None,
    )


@pytest.mark.parametrize(
    ("status", "prepared", "delegated"),
    [
        (ExecutionStatus.PENDING, True, True),
        (ExecutionStatus.PENDING, False, False),
        (ExecutionStatus.RUNNING, True, False),
        (ExecutionStatus.COMPLETED, True, False),
    ],
)
async def test_only_uncertain_pending_events_delegate(
    *, status: ExecutionStatus, prepared: bool, delegated: bool
) -> None:
    value = execution(status, prepared=prepared)
    instance, session = monitor(value)
    assert await instance._delivery_recovery_owns_missing_run(value.id) is delegated
    assert value.status == status
    session.commit.assert_not_awaited()


async def test_missing_run_preserves_pending_preparation(monkeypatch: pytest.MonkeyPatch) -> None:
    value = execution()
    instance, session = monitor(value)
    instance.temporal_client = MagicMock()
    instance._shutdown = False
    instance._initialize_monitoring = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(
        instance, "_run_monitor_loop", AsyncMock(side_effect=RPCError("missing", RPCStatusCode.NOT_FOUND, b""))
    )
    log = MagicMock()
    monkeypatch.setattr(module, "logger", log)
    await instance._monitor_execution(value.id, value.temporal_workflow_id)
    assert value.status == ExecutionStatus.PENDING
    assert value.execution_metadata == {"event_delivery": {"scheduling_state": "prepared"}}
    log.info.assert_any_call("Prepared event missing run delegated to delivery recovery", execution_id=value.id)
    session.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "failure",
    [
        OperationalError("lookup", {}, RuntimeError("PRIVATE")),
        InterfaceError("lookup", {}, RuntimeError("PRIVATE")),
        SATimeoutError("PRIVATE"),
    ],
)
@pytest.mark.parametrize("stage", ["session_entry", "lookup"])
async def test_missing_run_database_failure_ends_monitor_gracefully(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    stage: str,
) -> None:
    value = execution()
    instance, session = monitor(value)
    instance.temporal_client = MagicMock()
    instance._shutdown = False
    instance._initialize_monitoring = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(
        instance, "_run_monitor_loop", AsyncMock(side_effect=RPCError("missing", RPCStatusCode.NOT_FOUND, b""))
    )
    if stage == "session_entry":
        session.__aenter__.side_effect = failure
    else:
        session.get.side_effect = failure
    log = MagicMock()
    monkeypatch.setattr(module, "logger", log)

    await instance._monitor_execution(value.id, value.temporal_workflow_id)

    assert value.status == ExecutionStatus.PENDING
    assert value.execution_metadata == {"event_delivery": {"scheduling_state": "prepared"}}
    session.commit.assert_not_awaited()
    log.warning.assert_called_once_with(
        "Temporal error while monitoring execution, will not retry", execution_id=value.id
    )
    log.exception.assert_not_called()


async def test_other_rpc_errors_do_not_query_delivery_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    value = execution()
    instance, session = monitor(value)
    instance.temporal_client = MagicMock()
    instance._shutdown = False
    instance._initialize_monitoring = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(
        instance, "_run_monitor_loop", AsyncMock(side_effect=RPCError("unavailable", RPCStatusCode.UNAVAILABLE, b""))
    )
    log = MagicMock()
    monkeypatch.setattr(module, "logger", log)

    await instance._monitor_execution(value.id, value.temporal_workflow_id)

    session.get.assert_not_awaited()
    log.warning.assert_called_once_with(
        "Temporal error while monitoring execution, will not retry", execution_id=value.id
    )
