"""Unit tests for async activity completion methods in TemporalExecutionService."""

from unittest.mock import AsyncMock, Mock

import pytest
from temporalio.service import RPCError, RPCStatusCode

from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService


def _make_rpc_error(message: str) -> RPCError:
    return RPCError(message, status=RPCStatusCode.NOT_FOUND, raw_grpc_status=b"")


def _make_service() -> tuple[TemporalExecutionService, Mock]:
    """Create a TemporalExecutionService with mocked client."""
    mock_client = Mock()
    service = TemporalExecutionService(mock_client, "test-queue")
    return service, mock_client


class TestCompleteAsyncActivity:
    """Tests for TemporalExecutionService.complete_async_activity."""

    @pytest.mark.asyncio
    async def test_completes_activity_with_result(self) -> None:
        """Test that complete calls handle.complete with the result."""
        service, mock_client = _make_service()
        mock_handle = AsyncMock()
        mock_client.get_async_activity_handle.return_value = mock_handle

        await service.complete_async_activity("wf-123", "node-1", {"output": {"status": "ok"}})

        mock_client.get_async_activity_handle.assert_called_once_with(
            workflow_id="wf-123",
            run_id=None,
            activity_id="node-1",
        )
        mock_handle.complete.assert_called_once_with({"output": {"status": "ok"}})

    @pytest.mark.asyncio
    async def test_idempotent_on_not_found(self) -> None:
        """Test that RPCError with 'not found' is treated as a no-op."""
        service, mock_client = _make_service()
        mock_handle = AsyncMock()
        mock_handle.complete.side_effect = _make_rpc_error("activity not found")
        mock_client.get_async_activity_handle.return_value = mock_handle

        await service.complete_async_activity("wf-123", "node-1", {"output": {}})

    @pytest.mark.asyncio
    async def test_raises_on_other_rpc_error(self) -> None:
        """Test that non-'not found' RPCError is re-raised."""
        service, mock_client = _make_service()
        mock_handle = AsyncMock()
        mock_handle.complete.side_effect = RPCError(
            "connection refused",
            status=RPCStatusCode.UNAVAILABLE,
            raw_grpc_status=b"",
        )
        mock_client.get_async_activity_handle.return_value = mock_handle

        with pytest.raises(RPCError, match="connection refused"):
            await service.complete_async_activity("wf-123", "node-1", {"output": {}})


class TestFailAsyncActivity:
    """Tests for TemporalExecutionService.fail_async_activity."""

    @pytest.mark.asyncio
    async def test_fails_activity_with_error(self) -> None:
        """Test that fail calls handle.fail with the error."""
        service, mock_client = _make_service()
        mock_handle = AsyncMock()
        mock_client.get_async_activity_handle.return_value = mock_handle

        error = RuntimeError("agent crashed")
        await service.fail_async_activity("wf-123", "node-1", error)

        mock_client.get_async_activity_handle.assert_called_once_with(
            workflow_id="wf-123",
            run_id=None,
            activity_id="node-1",
        )
        mock_handle.fail.assert_called_once_with(error)

    @pytest.mark.asyncio
    async def test_idempotent_on_not_found(self) -> None:
        """Test that RPCError with 'not found' is treated as a no-op."""
        service, mock_client = _make_service()
        mock_handle = AsyncMock()
        mock_handle.fail.side_effect = _make_rpc_error("activity not found")
        mock_client.get_async_activity_handle.return_value = mock_handle

        await service.fail_async_activity("wf-123", "node-1", RuntimeError("err"))

    @pytest.mark.asyncio
    async def test_raises_on_other_rpc_error(self) -> None:
        """Test that non-'not found' RPCError is re-raised."""
        service, mock_client = _make_service()
        mock_handle = AsyncMock()
        mock_handle.fail.side_effect = RPCError(
            "connection refused",
            status=RPCStatusCode.UNAVAILABLE,
            raw_grpc_status=b"",
        )
        mock_client.get_async_activity_handle.return_value = mock_handle

        with pytest.raises(RPCError, match="connection refused"):
            await service.fail_async_activity("wf-123", "node-1", RuntimeError("err"))
