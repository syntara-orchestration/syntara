"""Unit tests for ExecutionService.cancel_execution method."""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.exceptions import (
    ExecutionInTerminalStateError,
    ExecutionNotFoundError,
    TemporalUnavailableError,
)
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.services.execution_service import ExecutionService
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService


def _make_execution(status: ExecutionStatus) -> Execution:
    execution = Mock(spec=Execution)
    execution.id = uuid4()
    execution.status = status
    execution.temporal_workflow_id = f"temporal-{execution.id}"
    execution.deleted_at = None
    return execution


def _mock_session_returning(execution: Execution | None) -> AsyncSession:
    mock_result = Mock()
    mock_result.one_or_none.return_value = execution
    mock_session = Mock(spec=AsyncSession)
    mock_session.exec = AsyncMock(return_value=mock_result)
    return mock_session


def _patch_approval_service(cancelled: list[object] | None = None):  # noqa: ANN202
    """Patch the ApprovalService used by cancel_execution to avoid a real DB call."""
    mock_instance = Mock()
    mock_instance.cancel_pending_for_execution = AsyncMock(return_value=cancelled if cancelled is not None else [])
    mock_instance.reopen_cancelled = AsyncMock()
    return (
        patch(
            "syntara.workflows.services.execution_service.ApprovalService",
            return_value=mock_instance,
        ),
        mock_instance,
    )


class TestCancelExecution:
    """Test cancel_execution method."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "execution_status",
        [
            ExecutionStatus.RUNNING,
            ExecutionStatus.PENDING,
            ExecutionStatus.PAUSED,
        ],
    )
    async def test_cancel_execution_success(self, execution_status: ExecutionStatus) -> None:
        """Test successful cancellation request is sent to Temporal."""
        execution = _make_execution(execution_status)
        mock_session = _mock_session_returning(execution)
        mock_user = Mock(spec=User)
        mock_temporal = Mock(spec=TemporalExecutionService)
        mock_temporal.cancel_workflow = AsyncMock()

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=mock_temporal,
        )

        patcher, mock_approval_service = _patch_approval_service()
        with patcher:
            await service.cancel_execution(execution.id)

        mock_temporal.cancel_workflow.assert_awaited_once_with(temporal_workflow_id=execution.temporal_workflow_id)
        mock_approval_service.cancel_pending_for_execution.assert_awaited_once_with(execution.id)
        mock_approval_service.reopen_cancelled.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cancel_execution_not_found(self) -> None:
        """Test cancellation when execution not found raises domain exception."""
        mock_session = _mock_session_returning(None)
        mock_user = Mock(spec=User)

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=None,
        )

        non_existent_id = uuid4()
        with pytest.raises(ExecutionNotFoundError) as exc_info:
            await service.cancel_execution(non_existent_id)

        assert exc_info.value.execution_id == non_existent_id

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "terminal_status",
        [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        ],
    )
    async def test_cancel_execution_terminal_state(self, terminal_status: ExecutionStatus) -> None:
        """Test cancellation when execution in terminal state raises domain exception."""
        execution = _make_execution(terminal_status)
        mock_session = _mock_session_returning(execution)
        mock_user = Mock(spec=User)
        mock_temporal = Mock(spec=TemporalExecutionService)

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=mock_temporal,
        )

        with pytest.raises(ExecutionInTerminalStateError) as exc_info:
            await service.cancel_execution(execution.id)

        assert exc_info.value.execution_id == execution.id
        assert exc_info.value.status == terminal_status.value
        assert exc_info.value.operation == "cancel"

    @pytest.mark.asyncio
    async def test_cancel_execution_temporal_unavailable(self) -> None:
        """Test cancellation when Temporal service unavailable raises domain exception."""
        execution = _make_execution(ExecutionStatus.RUNNING)
        mock_session = _mock_session_returning(execution)
        mock_user = Mock(spec=User)

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=None,
        )

        with pytest.raises(TemporalUnavailableError) as exc_info:
            await service.cancel_execution(execution.id)

        assert exc_info.value.operation == "workflow cancellation"

    @pytest.mark.asyncio
    async def test_cancel_execution_temporal_rpc_error_propagates(self) -> None:
        """Test that Temporal RPC errors propagate to the caller."""
        from temporalio.service import RPCError, RPCStatusCode

        execution = _make_execution(ExecutionStatus.RUNNING)
        mock_session = _mock_session_returning(execution)
        mock_user = Mock(spec=User)
        mock_temporal = Mock(spec=TemporalExecutionService)
        mock_temporal.cancel_workflow = AsyncMock(
            side_effect=RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b""),
        )

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=mock_temporal,
        )

        patcher, _mock_approval_service = _patch_approval_service()
        with patcher, pytest.raises(RPCError):
            await service.cancel_execution(execution.id)

    @pytest.mark.asyncio
    async def test_cancel_execution_temporal_failure_reverts_approval_cancellation(self) -> None:
        """A failed Temporal cancel RPC reverts the approvals that were just cancelled.

        Guards against a partial state: leaving approvals cancelled for an
        execution that Temporal never actually agreed to cancel.
        """
        execution = _make_execution(ExecutionStatus.RUNNING)
        mock_session = _mock_session_returning(execution)
        mock_user = Mock(spec=User)
        mock_temporal = Mock(spec=TemporalExecutionService)
        mock_temporal.cancel_workflow = AsyncMock(side_effect=RuntimeError("temporal unreachable"))

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=mock_temporal,
        )

        cancelled = [Mock()]
        patcher, mock_approval_service = _patch_approval_service(cancelled=cancelled)
        with patcher, pytest.raises(RuntimeError):
            await service.cancel_execution(execution.id)

        mock_approval_service.cancel_pending_for_execution.assert_awaited_once_with(execution.id)
        mock_approval_service.reopen_cancelled.assert_awaited_once_with(cancelled)

    @pytest.mark.asyncio
    async def test_cancel_execution_original_error_survives_a_failed_revert(self) -> None:
        """The original Temporal error propagates even if reopen_cancelled() itself fails.

        If both the Temporal RPC and the compensating revert fail, the caller must
        still see the Temporal failure (not the revert's), and approvals may be
        left incorrectly cancelled -- but that's a logged, visible failure rather
        than a silently swallowed one.
        """
        execution = _make_execution(ExecutionStatus.RUNNING)
        mock_session = _mock_session_returning(execution)
        mock_user = Mock(spec=User)
        mock_temporal = Mock(spec=TemporalExecutionService)
        mock_temporal.cancel_workflow = AsyncMock(side_effect=RuntimeError("temporal unreachable"))

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=mock_temporal,
        )

        patcher, mock_approval_service = _patch_approval_service(cancelled=[Mock()])
        mock_approval_service.reopen_cancelled = AsyncMock(side_effect=RuntimeError("db unreachable during revert"))
        with patcher, pytest.raises(RuntimeError, match="temporal unreachable"):
            await service.cancel_execution(execution.id)

    @pytest.mark.asyncio
    async def test_cancel_execution_cancels_pending_approvals_before_temporal_rpc(self) -> None:
        """cancel_execution cancels pending approvals before asking Temporal to cancel.

        This closes the race window (AAP bug: cancelled execution + approved
        approval) that previously existed while cancellation depended solely on
        the workflow engine's async, best-effort cleanup activity, or on a
        synchronous cancel issued only after the Temporal RPC returned.
        """
        execution = _make_execution(ExecutionStatus.RUNNING)
        mock_session = _mock_session_returning(execution)
        mock_user = Mock(spec=User)
        mock_temporal = Mock(spec=TemporalExecutionService)

        call_order: list[str] = []
        cancelled = [Mock()]

        async def _fake_cancel_pending_for_execution(_execution_id: object) -> list[object]:
            call_order.append("cancel_approvals")
            return cancelled

        async def _fake_temporal_cancel(**_kwargs: object) -> None:
            call_order.append("temporal_cancel")

        mock_temporal.cancel_workflow = AsyncMock(side_effect=_fake_temporal_cancel)

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=mock_temporal,
        )

        patcher, mock_approval_service = _patch_approval_service(cancelled=cancelled)
        mock_approval_service.cancel_pending_for_execution.side_effect = _fake_cancel_pending_for_execution
        with patcher as mock_approval_service_cls:
            await service.cancel_execution(execution.id)

        mock_approval_service_cls.assert_called_once_with(mock_session, mock_user)
        mock_approval_service.cancel_pending_for_execution.assert_awaited_once_with(execution.id)
        mock_approval_service.reopen_cancelled.assert_not_awaited()
        assert call_order == ["cancel_approvals", "temporal_cancel"]
