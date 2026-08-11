"""Unit tests for ExecutionService.cancel_execution method."""

from unittest.mock import AsyncMock, Mock
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
