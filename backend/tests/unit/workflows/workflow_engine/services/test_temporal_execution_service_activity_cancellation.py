"""Unit tests for async Temporal activity cancellation reporting."""

from unittest.mock import AsyncMock, Mock

import pytest
from temporalio.client import AsyncActivityHandle, Client

from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService


@pytest.mark.asyncio
async def test_report_cancellation_async_activity_uses_matching_handle() -> None:
    mock_client = Mock(spec=Client)
    mock_handle = AsyncMock(spec=AsyncActivityHandle)
    mock_client.get_async_activity_handle = Mock(return_value=mock_handle)
    service = TemporalExecutionService(temporal_client=mock_client, task_queue="test-queue")

    await service.report_cancellation_async_activity(
        temporal_workflow_id="workflow-id",
        activity_id="activity-id",
    )

    mock_client.get_async_activity_handle.assert_called_once_with(
        workflow_id="workflow-id",
        run_id=None,
        activity_id="activity-id",
    )
    mock_handle.report_cancellation.assert_awaited_once()
