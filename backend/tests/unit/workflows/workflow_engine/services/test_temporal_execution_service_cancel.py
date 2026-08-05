"""Unit tests for TemporalExecutionService.cancel_workflow method."""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from temporalio.client import Client, WorkflowHandle
from temporalio.exceptions import TemporalError
from temporalio.service import RPCError, RPCStatusCode

from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService


class TestCancelWorkflow:
    """Test cancel_workflow method."""

    @pytest.mark.asyncio
    async def test_cancel_workflow_success(self) -> None:
        """Test successful workflow cancellation."""
        mock_client = Mock(spec=Client)
        mock_handle = AsyncMock(spec=WorkflowHandle)
        mock_client.get_workflow_handle = Mock(return_value=mock_handle)

        service = TemporalExecutionService(
            temporal_client=mock_client,
            task_queue="test-queue",
        )

        temporal_workflow_id = f"test-workflow-{uuid4()}"
        await service.cancel_workflow(temporal_workflow_id=temporal_workflow_id)

        mock_client.get_workflow_handle.assert_called_once_with(temporal_workflow_id)
        mock_handle.cancel.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_workflow_temporal_error(self) -> None:
        """Test workflow cancellation when Temporal raises error."""
        mock_client = Mock(spec=Client)
        mock_handle = AsyncMock(spec=WorkflowHandle)
        mock_handle.cancel = AsyncMock(side_effect=TemporalError("Temporal error"))
        mock_client.get_workflow_handle = Mock(return_value=mock_handle)

        service = TemporalExecutionService(
            temporal_client=mock_client,
            task_queue="test-queue",
        )

        with pytest.raises(TemporalError):
            await service.cancel_workflow(temporal_workflow_id=f"test-workflow-{uuid4()}")

    @pytest.mark.asyncio
    async def test_cancel_workflow_calls_correct_handle(self) -> None:
        """Test that cancel_workflow gets the correct workflow handle."""
        mock_client = Mock(spec=Client)
        mock_handle = AsyncMock(spec=WorkflowHandle)
        mock_client.get_workflow_handle = Mock(return_value=mock_handle)

        service = TemporalExecutionService(
            temporal_client=mock_client,
            task_queue="test-queue",
        )

        await service.cancel_workflow(temporal_workflow_id="specific-workflow-id-123")

        mock_client.get_workflow_handle.assert_called_once_with("specific-workflow-id-123")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED])
    async def test_cancel_workflow_invalidates_client_on_connection_error(self, status: RPCStatusCode) -> None:
        mock_client = Mock(spec=Client)
        mock_handle = AsyncMock(spec=WorkflowHandle)
        mock_handle.cancel = AsyncMock(side_effect=RPCError("err", status=status, raw_grpc_status=b""))
        mock_client.get_workflow_handle = Mock(return_value=mock_handle)

        service = TemporalExecutionService(temporal_client=mock_client, task_queue="test-queue")

        with (
            patch("syntara.core.temporal.client.invalidate_client") as mock_invalidate,
            pytest.raises(RPCError),
        ):
            await service.cancel_workflow(temporal_workflow_id=f"test-workflow-{uuid4()}")

        mock_invalidate.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_workflow_does_not_invalidate_on_non_connection_error(self) -> None:
        mock_client = Mock(spec=Client)
        mock_handle = AsyncMock(spec=WorkflowHandle)
        mock_handle.cancel = AsyncMock(
            side_effect=RPCError("bad", status=RPCStatusCode.INVALID_ARGUMENT, raw_grpc_status=b"")
        )
        mock_client.get_workflow_handle = Mock(return_value=mock_handle)

        service = TemporalExecutionService(temporal_client=mock_client, task_queue="test-queue")

        with (
            patch("syntara.core.temporal.client.invalidate_client") as mock_invalidate,
            pytest.raises(RPCError),
        ):
            await service.cancel_workflow(temporal_workflow_id=f"test-workflow-{uuid4()}")

        mock_invalidate.assert_not_called()
