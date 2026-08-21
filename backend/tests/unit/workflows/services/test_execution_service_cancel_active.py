"""Unit tests for ExecutionService bulk cancellation used by workflow deletion.

Covers ``cancel_active_executions``, ``finalize_gone_executions`` and
``cancel_pending_approvals_for_executions`` (AAP-87750).
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import ClauseElement
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.service import RPCError, RPCStatusCode

from syntara.core.models import User
from syntara.workflows.exceptions import TemporalUnavailableError
from syntara.workflows.models.execution import Execution, ExecutionMode, ExecutionStatus
from syntara.workflows.services.execution_service import ExecutionCancellationResult, ExecutionService
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService


def _make_execution(
    status: ExecutionStatus = ExecutionStatus.PAUSED,
    *,
    launcher_id: str | None = None,
) -> Execution:
    execution = Mock(spec=Execution)
    execution.id = uuid4()
    execution.workflow_id = uuid4()
    execution.status = status
    execution.mode = ExecutionMode.STANDARD
    execution.temporal_workflow_id = f"temporal-{execution.id}"
    execution.launcher_temporal_workflow_id = launcher_id
    return execution


def _session_returning(executions: list[Execution]) -> AsyncSession:
    result = Mock()
    result.all.return_value = executions
    session = Mock(spec=AsyncSession)
    session.exec = AsyncMock(return_value=result)
    return session


def _service(session: AsyncSession, temporal: TemporalExecutionService | None) -> ExecutionService:
    user = Mock(spec=User)
    user.id = uuid4()
    user.display_name = "Test User"
    return ExecutionService(session=session, user=user, temporal_service=temporal)


def _temporal(*, cancelled: bool = True) -> Any:  # noqa: ANN401
    """Temporal stub. ``cancelled=False`` mimics a run Temporal has no record of."""
    temporal = Mock(spec=TemporalExecutionService)
    temporal.cancel_workflow = AsyncMock(return_value=cancelled)
    return temporal


def _real_temporal_service(cancel: AsyncMock) -> TemporalExecutionService:
    handle = Mock()
    handle.cancel = cancel
    client = Mock()
    client.get_workflow_handle = Mock(return_value=handle)
    return TemporalExecutionService(temporal_client=client, task_queue="q")


def _compiled(statement: ClauseElement) -> str:
    """Render a statement so SQL-level guarantees can be asserted directly."""
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]


class TestCancelActiveExecutions:
    """Temporal-side cancellation of a workflow's in-flight executions."""

    @pytest.mark.asyncio
    async def test_cancels_every_active_execution(self) -> None:
        executions = [_make_execution(), _make_execution(ExecutionStatus.RUNNING)]
        temporal = _temporal()
        service = _service(_session_returning(executions), temporal)

        with patch("syntara.workflows.services.execution_service.AuditEventDispatcher"):
            result = await service.cancel_active_executions(workflow_id=uuid4())

        assert result.requested == [e.id for e in executions]
        assert result.already_gone == []
        assert temporal.cancel_workflow.await_count == 2
        cancelled_ids = {c.kwargs["temporal_workflow_id"] for c in temporal.cancel_workflow.await_args_list}
        assert cancelled_ids == {e.temporal_workflow_id for e in executions}

    @pytest.mark.asyncio
    async def test_runs_temporal_has_no_record_of_are_reported_separately(self) -> None:
        """These get no completion event, so the caller must finalise them itself."""
        execution = _make_execution()
        service = _service(_session_returning([execution]), _temporal(cancelled=False))

        with patch("syntara.workflows.services.execution_service.AuditEventDispatcher"):
            result = await service.cancel_active_executions(workflow_id=uuid4())

        assert result.requested == []
        assert result.already_gone == [execution.id]
        assert result.all_ids == [execution.id]

    @pytest.mark.asyncio
    async def test_returns_empty_and_skips_temporal_when_nothing_active(self) -> None:
        """A Temporal outage must not block deleting a workflow that has no runs."""
        temporal = _temporal()
        service = _service(_session_returning([]), temporal)

        result = await service.cancel_active_executions(workflow_id=uuid4())

        assert result.all_ids == []
        temporal.cancel_workflow.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_temporal_service_with_no_executions_succeeds(self) -> None:
        service = _service(_session_returning([]), None)

        assert (await service.cancel_active_executions(workflow_id=uuid4())).all_ids == []

    @pytest.mark.asyncio
    async def test_no_temporal_service_with_active_executions_raises(self) -> None:
        service = _service(_session_returning([_make_execution()]), None)

        with pytest.raises(TemporalUnavailableError):
            await service.cancel_active_executions(workflow_id=uuid4())

    @pytest.mark.asyncio
    async def test_cancels_launcher_for_scheduled_executions(self) -> None:
        """Scheduled runs cancel the parent launcher, not the child orchestrator.

        Between the execution row being committed and the child being started, the
        child does not exist yet, so cancelling it would be a silent no-op.
        """
        execution = _make_execution(launcher_id="scheduled-launcher-1")
        temporal = _temporal()
        service = _service(_session_returning([execution]), temporal)

        with patch("syntara.workflows.services.execution_service.AuditEventDispatcher"):
            await service.cancel_active_executions(workflow_id=uuid4())

        temporal.cancel_workflow.assert_awaited_once_with(temporal_workflow_id="scheduled-launcher-1")

    @pytest.mark.asyncio
    async def test_awaits_all_cancels_before_raising_on_partial_failure(self) -> None:
        """gather() is not fail-fast, so every cancel must be attempted, then the error raised.

        Partial cancellation is unavoidable here: each cancel is an independent
        external call.  The contract is that the caller aborts the delete.
        """
        executions = [_make_execution() for _ in range(3)]
        failing_id = executions[1].temporal_workflow_id
        attempted: list[str] = []

        async def cancel(*, temporal_workflow_id: str) -> bool:
            attempted.append(temporal_workflow_id)
            if temporal_workflow_id == failing_id:
                msg = "temporal exploded"
                raise RuntimeError(msg)
            return True

        temporal = Mock(spec=TemporalExecutionService)
        temporal.cancel_workflow = AsyncMock(side_effect=cancel)
        service = _service(_session_returning(executions), temporal)

        with (
            patch("syntara.workflows.services.execution_service.AuditEventDispatcher"),
            pytest.raises(RuntimeError, match="temporal exploded"),
        ):
            await service.cancel_active_executions(workflow_id=uuid4())

        # All three attempted despite the middle one failing.
        assert sorted(attempted) == sorted(e.temporal_workflow_id for e in executions)


class TestFinalizeGoneExecutions:
    """Rows Temporal has no run for must be driven terminal locally."""

    @pytest.mark.asyncio
    async def test_no_ids_is_a_noop(self) -> None:
        session = Mock(spec=AsyncSession)
        session.execute = AsyncMock()
        service = _service(session, None)

        assert await service.finalize_gone_executions([]) == 0
        session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sets_cancelled_and_leaves_terminal_rows_alone(self) -> None:
        execution_id = uuid4()
        result = Mock()
        result.all.return_value = [(execution_id,)]
        session = Mock(spec=AsyncSession)
        session.execute = AsyncMock(return_value=result)
        session.run_sync = AsyncMock()
        service = _service(session, None)

        assert await service.finalize_gone_executions([execution_id]) == 1

        sql = _compiled(session.execute.await_args.args[0])
        assert "UPDATE executions" in sql
        # completed_at must satisfy check_execution_completed_at_after_created_at
        assert "greatest" in sql.lower()
        assert "NOT IN" in sql, "terminal executions must not be re-finalised"
        assert "RETURNING" in sql

    @pytest.mark.asyncio
    async def test_does_not_commit(self) -> None:
        result = Mock()
        result.all.return_value = []
        session = Mock(spec=AsyncSession)
        session.execute = AsyncMock(return_value=result)
        session.run_sync = AsyncMock()
        session.commit = AsyncMock()
        service = _service(session, None)

        await service.finalize_gone_executions([uuid4()])

        session.commit.assert_not_awaited()


class TestCancelPendingApprovalsForExecutions:
    """System-level bulk cancellation of approvals belonging to a deleted workflow."""

    @pytest.mark.asyncio
    async def test_no_executions_is_a_noop(self) -> None:
        session = Mock(spec=AsyncSession)
        session.execute = AsyncMock()
        service = _service(session, None)

        assert await service.cancel_pending_approvals_for_executions([], decided_by=uuid4()) == 0
        session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_audit_context_is_applied_before_the_dml(self) -> None:
        """Core DML bypasses before_flush, so actor context must be set first.

        Asserts real ordering *and* that the callable handed to run_sync actually
        invokes apply_audit_context — a bare AsyncMock would let an empty lambda pass.
        """
        calls: list[str] = []
        sync_session = Mock()

        async def run_sync(fn: Any) -> None:  # noqa: ANN401
            fn(sync_session)

        result = Mock()
        result.all.return_value = []
        session = Mock(spec=AsyncSession)
        session.run_sync = AsyncMock(side_effect=run_sync)

        async def execute(*_args: Any, **_kwargs: Any) -> Mock:  # noqa: ANN401
            calls.append("dml")
            return result

        session.execute = AsyncMock(side_effect=execute)
        service = _service(session, None)

        with patch("syntara.core.database.session.apply_audit_context") as apply_ctx:
            apply_ctx.side_effect = lambda _s: calls.append("audit_context")
            await service.cancel_pending_approvals_for_executions([uuid4()], decided_by=uuid4())

        apply_ctx.assert_called_once_with(sync_session)
        assert calls == ["audit_context", "dml"], "audit context must be set before the UPDATE"

    @pytest.mark.asyncio
    async def test_update_targets_only_pending_approvals(self) -> None:
        """The PENDING guard lives in SQL, so assert it in the compiled statement."""
        result = Mock()
        result.all.return_value = []
        session = Mock(spec=AsyncSession)
        session.execute = AsyncMock(return_value=result)
        session.run_sync = AsyncMock()
        service = _service(session, None)

        await service.cancel_pending_approvals_for_executions([uuid4()], decided_by=uuid4())

        sql = _compiled(session.execute.await_args.args[0])
        assert "UPDATE approval_requests" in sql
        assert "approval_requests.status = " in sql, "missing the PENDING-only guard"
        assert "execution_id IN" in sql
        assert "RETURNING" in sql

    @pytest.mark.asyncio
    async def test_dispatches_one_event_per_approval_within_the_caller_transaction(self) -> None:
        execution_id = uuid4()
        decider = uuid4()
        created_at = datetime.now(UTC)
        rows = [
            (uuid4(), execution_id, "approval_gate", created_at),
            (uuid4(), execution_id, "second_gate", created_at),
        ]
        result = Mock()
        result.all.return_value = rows
        session = Mock(spec=AsyncSession)
        session.execute = AsyncMock(return_value=result)
        session.run_sync = AsyncMock()
        session.sync_session = Mock()
        service = _service(session, None)

        with patch("syntara.workflows.services.execution_service.AuditEventDispatcher") as dispatcher:
            count = await service.cancel_pending_approvals_for_executions([execution_id], decided_by=decider)

        assert count == 2
        assert dispatcher.dispatch.call_count == 2
        for call, (approval_id, _exec_id, node_id, _created) in zip(
            dispatcher.dispatch.call_args_list, rows, strict=True
        ):
            event = call.args[0]
            assert event.approval_id == approval_id
            assert event.approval_node_id == node_id
            assert event.decision == "cancelled"
            assert event.decision_notes == "Workflow was deleted"
            assert event.decided_by == decider
            # passing the session keeps the outbox write in the caller's transaction,
            # so a rolled-back delete emits no cancellation events
            assert call.kwargs["session"] is session.sync_session

    @pytest.mark.asyncio
    async def test_does_not_commit(self) -> None:
        """The caller owns the transaction."""
        result = Mock()
        result.all.return_value = []
        session = Mock(spec=AsyncSession)
        session.execute = AsyncMock(return_value=result)
        session.run_sync = AsyncMock()
        session.sync_session = Mock()
        session.commit = AsyncMock()
        service = _service(session, None)

        await service.cancel_pending_approvals_for_executions([uuid4()], decided_by=uuid4())

        session.commit.assert_not_awaited()


class TestCancelWorkflowNotFoundDetection:
    """A closed run must be detected by gRPC status, not by message text."""

    @pytest.mark.asyncio
    async def test_already_completed_message_is_classified_as_gone(self) -> None:
        # Temporal's wording for a closed run contains no "not found" substring.
        cancel = AsyncMock(side_effect=RPCError("workflow execution already completed", RPCStatusCode.NOT_FOUND, b""))
        service = _real_temporal_service(cancel)

        assert await service.cancel_workflow(temporal_workflow_id="wf-1") is False

    @pytest.mark.asyncio
    async def test_other_rpc_errors_still_propagate(self) -> None:
        cancel = AsyncMock(side_effect=RPCError("unavailable", RPCStatusCode.UNAVAILABLE, b""))
        service = _real_temporal_service(cancel)

        with pytest.raises(RPCError):
            await service.cancel_workflow(temporal_workflow_id="wf-1")

    @pytest.mark.asyncio
    async def test_successful_cancel_returns_true(self) -> None:
        service = _real_temporal_service(AsyncMock())

        assert await service.cancel_workflow(temporal_workflow_id="wf-1") is True


def test_cancellation_result_shape() -> None:
    """Guard against the result tuple silently changing shape."""
    a, b = uuid4(), uuid4()
    result = ExecutionCancellationResult(requested=[a], already_gone=[b])
    assert result.all_ids == [a, b]
    assert all(isinstance(i, UUID) for i in result.all_ids)
