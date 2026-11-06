"""Unit tests for ExecutionService.cancel_execution method."""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.services.invocation_service import InvocationService
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
    return execution


def _mock_session_returning(execution: Execution | None) -> AsyncSession:
    mock_result = Mock()
    mock_result.one_or_none.return_value = execution
    mock_session = Mock(spec=AsyncSession)
    mock_session.exec = AsyncMock(return_value=mock_result)
    return mock_session


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

        with patch(
            "syntara.workflows.services.invocation_cancellation.cancel_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await service.cancel_execution(execution.id)

        mock_temporal.cancel_workflow.assert_awaited_once_with(temporal_workflow_id=execution.temporal_workflow_id)

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

        with pytest.raises(RPCError):
            await service.cancel_execution(execution.id)

    @pytest.mark.asyncio
    async def test_cancel_execution_injects_a_wired_invocation_service(self) -> None:
        """Invocation cancellation is delegated to a service built here.

        ExecutionService cancels its own workflow and hands the rest to
        cancel_invocations_for_execution; it no longer reaches into the builtin
        agent execution itself. It owns temporal_service, so it is the one that
        constructs the InvocationService with it rather than passing the
        dependency through a bridge module that never uses it.
        """
        execution = _make_execution(ExecutionStatus.RUNNING)
        mock_session = _mock_session_returning(execution)
        mock_user = Mock(spec=User)
        mock_temporal = Mock(spec=TemporalExecutionService)
        mock_temporal.cancel_workflow = AsyncMock()

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=mock_temporal,
        )

        with patch(
            "syntara.workflows.services.invocation_cancellation.cancel_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_cancel:
            await service.cancel_execution(execution.id)

        mock_cancel.assert_awaited_once()
        assert mock_cancel.await_args is not None
        session_arg, execution_id_arg, invocation_service = mock_cancel.await_args.args
        assert session_arg is mock_session
        assert execution_id_arg == execution.id
        # The injected service must carry the Temporal dependency: it owns the
        # cancel of the builtin workflow running each invocation, and without it
        # that half of the cancel is silently skipped.
        assert isinstance(invocation_service, InvocationService)
        assert invocation_service.temporal_service is mock_temporal
        assert invocation_service.user is mock_user
        # Only the user's own execution is cancelled from here; the per-invocation
        # Temporal cancel now happens inside InvocationService.
        mock_temporal.cancel_workflow.assert_awaited_once_with(temporal_workflow_id=execution.temporal_workflow_id)

    @pytest.mark.asyncio
    async def test_cancel_execution_invocation_failure_does_not_block(self) -> None:
        """Test that invocation cancel failure does not prevent execution cancel."""
        execution = _make_execution(ExecutionStatus.RUNNING)
        mock_session = _mock_session_returning(execution)
        mock_user = Mock(spec=User)
        mock_temporal = Mock(spec=TemporalExecutionService)
        mock_temporal.cancel_workflow = AsyncMock()

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=mock_temporal,
        )

        with patch(
            "syntara.workflows.services.invocation_cancellation.cancel_invocations_for_execution",
            new_callable=AsyncMock,
            side_effect=Exception("DB unavailable"),
        ):
            await service.cancel_execution(execution.id)

        mock_temporal.cancel_workflow.assert_awaited_once()
