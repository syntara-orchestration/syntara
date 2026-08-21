"""Unit tests for delete_workflow's cancel-then-delete ordering (AAP-87750).

The invariant under test: Temporal cancellation is an irreversible external side
effect, so it happens before any DB mutation.  If it fails, nothing is written and
the workflow survives, which is recoverable by retrying the delete.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID, uuid4

import pytest

from syntara.workflows.exceptions import (
    TemporalUnavailableError,
    WorkflowDeleteConflictError,
)
from syntara.workflows.services.execution_service import ExecutionCancellationResult
from syntara.workflows.services.workflow_service import WorkflowService


@pytest.fixture
def service() -> WorkflowService:
    """WorkflowService with mocked session and no execution service."""
    svc = WorkflowService.__new__(WorkflowService)
    session = AsyncMock()
    session.add = MagicMock()
    svc.session = session
    user = MagicMock()
    user.id = uuid4()
    svc.user = user
    svc.execution_service = None
    return svc


def _session(service: WorkflowService) -> Any:  # noqa: ANN401
    """The mocked session, typed loosely so tests can stub its methods."""
    return service.session


def _workflow(workflow_id: UUID) -> MagicMock:
    workflow = MagicMock()
    workflow.id = workflow_id
    workflow.is_builtin = False
    workflow.name = "test-wf"
    workflow.project_id = uuid4()
    return workflow


def _exec_results(
    active_before: list[UUID],
    active_after: list[UUID],
    workflow: MagicMock,
    all_ids: list[UUID] | None = None,
) -> list[Mock]:
    """Query results in delete_workflow order.

    1. active executions (phase 1)
    2. the FOR UPDATE re-fetch
    3. the active re-check (phase 3)
    4. every execution id, for approval cancellation
    5. the disassociating UPDATE
    """
    first = Mock()
    first.all = Mock(return_value=active_before)
    locked = Mock()
    locked.one_or_none = Mock(return_value=workflow)
    second = Mock()
    second.all = Mock(return_value=active_after)
    every = Mock()
    every.all = Mock(return_value=all_ids if all_ids is not None else active_after)
    return [first, locked, second, every, Mock()]


def _cancellation(requested: list[UUID] | None = None, gone: list[UUID] | None = None) -> Any:  # noqa: ANN401
    return ExecutionCancellationResult(requested=requested or [], already_gone=gone or [])


class TestDeleteWorkflowCancelsRuns:
    """Cancellation happens, and happens first."""

    @pytest.mark.asyncio
    async def test_cancels_active_executions_before_deleting(self, service: WorkflowService) -> None:
        workflow_id = uuid4()
        workflow = _workflow(workflow_id)
        execution_id = uuid4()
        order: list[str] = []

        def record_cancel(**_kwargs: object) -> Any:  # noqa: ANN401
            order.append("cancel")
            return _cancellation(requested=[execution_id])

        def record_approvals(*_args: object, **_kwargs: object) -> None:
            order.append("approvals")

        execution_service = Mock()
        execution_service.cancel_active_executions = AsyncMock(side_effect=record_cancel)
        execution_service.cancel_pending_approvals_for_executions = AsyncMock(side_effect=record_approvals)
        execution_service.finalize_gone_executions = AsyncMock(return_value=0)
        service.execution_service = execution_service
        _session(service).delete = AsyncMock(side_effect=lambda *_: order.append("delete"))
        _session(service).commit = AsyncMock(side_effect=lambda: order.append("commit"))
        _session(service).exec = AsyncMock(side_effect=_exec_results([execution_id], [execution_id], workflow))

        with (
            patch.object(service, "get_workflow_by_id", new_callable=AsyncMock, return_value=workflow),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as wh,
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as sched,
        ):
            wh.return_value.delete_triggers_for_workflow = AsyncMock()
            sched.return_value.delete_triggers_for_workflow = AsyncMock()
            await service.delete_workflow(workflow_id)

        assert order == ["commit", "cancel", "approvals", "delete", "commit"]
        execution_service.cancel_active_executions.assert_awaited_once_with(
            workflow_id=workflow_id, workflow_name="test-wf"
        )
        execution_service.cancel_pending_approvals_for_executions.assert_awaited_once_with(
            [execution_id], decided_by=service.user.id
        )
        # phase 1 ends its read transaction with commit(), not rollback()
        _session(service).rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_temporal_failure_leaves_workflow_undeleted(self, service: WorkflowService) -> None:
        workflow_id = uuid4()
        workflow = _workflow(workflow_id)

        execution_service = Mock()
        execution_service.cancel_active_executions = AsyncMock(side_effect=TemporalUnavailableError("cancel"))
        execution_service.finalize_gone_executions = AsyncMock(return_value=0)
        service.execution_service = execution_service
        _session(service).delete = AsyncMock()
        _session(service).commit = AsyncMock()
        _session(service).exec = AsyncMock(side_effect=_exec_results([uuid4()], [], workflow))

        with (
            patch.object(service, "get_workflow_by_id", new_callable=AsyncMock, return_value=workflow),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService"),
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService"),
            pytest.raises(TemporalUnavailableError),
        ):
            await service.delete_workflow(workflow_id)

        _session(service).delete.assert_not_awaited()
        # only phase 1's read-transaction commit; the delete itself never committed
        assert _session(service).commit.await_count == 1

    @pytest.mark.asyncio
    async def test_no_executions_deletes_without_touching_temporal(self, service: WorkflowService) -> None:
        """A Temporal outage must not make never-run workflows undeletable."""
        workflow_id = uuid4()
        workflow = _workflow(workflow_id)
        service.execution_service = None  # stands in for no Temporal client
        _session(service).delete = AsyncMock()
        _session(service).commit = AsyncMock()
        _session(service).exec = AsyncMock(side_effect=_exec_results([], [], workflow))

        with (
            patch.object(service, "get_workflow_by_id", new_callable=AsyncMock, return_value=workflow),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as wh,
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService") as sched,
        ):
            wh.return_value.delete_triggers_for_workflow = AsyncMock()
            sched.return_value.delete_triggers_for_workflow = AsyncMock()
            await service.delete_workflow(workflow_id)

        _session(service).delete.assert_awaited_once()
        # phase 1 read commit + the delete commit
        assert _session(service).commit.await_count == 2

    @pytest.mark.asyncio
    async def test_active_runs_without_execution_service_refuses(self, service: WorkflowService) -> None:
        workflow_id = uuid4()
        workflow = _workflow(workflow_id)
        service.execution_service = None
        _session(service).delete = AsyncMock()
        _session(service).commit = AsyncMock()
        _session(service).exec = AsyncMock(side_effect=_exec_results([uuid4()], [], workflow))

        with (
            patch.object(service, "get_workflow_by_id", new_callable=AsyncMock, return_value=workflow),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService"),
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService"),
            pytest.raises(TemporalUnavailableError),
        ):
            await service.delete_workflow(workflow_id)

        _session(service).delete.assert_not_awaited()


class TestDeleteWorkflowConflict:
    """An execution that starts mid-delete must not be silently orphaned."""

    @pytest.mark.asyncio
    async def test_newly_started_execution_raises_conflict(self, service: WorkflowService) -> None:
        workflow_id = uuid4()
        workflow = _workflow(workflow_id)
        known, appeared = uuid4(), uuid4()

        execution_service = Mock()
        execution_service.cancel_active_executions = AsyncMock(return_value=_cancellation(requested=[known]))
        execution_service.cancel_pending_approvals_for_executions = AsyncMock()
        execution_service.finalize_gone_executions = AsyncMock(return_value=0)
        service.execution_service = execution_service
        _session(service).delete = AsyncMock()
        _session(service).commit = AsyncMock()
        _session(service).exec = AsyncMock(side_effect=_exec_results([known], [known, appeared], workflow))

        with (
            patch.object(service, "get_workflow_by_id", new_callable=AsyncMock, return_value=workflow),
            patch("syntara.workflows.services.workflow_service.AuditEventDispatcher"),
            patch("syntara.workflows.services.workflow_service.WebhookTriggerService"),
            patch("syntara.workflows.services.workflow_service.ScheduledTriggerService"),
            pytest.raises(WorkflowDeleteConflictError) as exc_info,
        ):
            await service.delete_workflow(workflow_id)

        assert exc_info.value.execution_count == 1
        assert exc_info.value.workflow_name == "test-wf"
        _session(service).delete.assert_not_awaited()
        # only phase 1's read-transaction commit
        assert _session(service).commit.await_count == 1
