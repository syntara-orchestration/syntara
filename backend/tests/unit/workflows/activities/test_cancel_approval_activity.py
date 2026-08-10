"""Unit tests for cancel approval activity.

Tests cancelling pending approval requests when a workflow is cancelled.
"""

from contextlib import AbstractContextManager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.workflows.workflow_engine.activities.approval_activity import (
    cancel_approval_requests_activity,
)


@pytest.fixture
def execution_id() -> str:
    """Workflow execution ID."""
    return str(uuid4())


@pytest.fixture
def pending_approvals() -> list[dict[str, Any]]:
    """Two pending approval requests across different nodes."""
    return [
        {"id": str(uuid4()), "approval_node_id": "approval_1", "status": "pending"},
        {"id": str(uuid4()), "approval_node_id": "approval_2", "status": "pending"},
    ]


def _mock_client(pending: list[dict[str, Any]], cancel_result: dict[str, Any] | None = None) -> AsyncMock:
    client = AsyncMock()
    client.list_approvals_by_execution = AsyncMock(return_value=pending)
    client.batch_cancel = AsyncMock(return_value=cancel_result or {"total_success": len(pending), "total_failed": 0})
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


def _patch_client(mock_client: AsyncMock) -> AbstractContextManager[MagicMock]:
    return patch(
        "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
        return_value=mock_client,
    )


@pytest.mark.asyncio
async def test_cancel_success(execution_id: str, pending_approvals: list[dict[str, Any]]) -> None:
    """All pending approvals are batch-cancelled."""
    client = _mock_client(pending_approvals)

    with _patch_client(client):
        result = await cancel_approval_requests_activity(execution_id)

    assert result["cancelled_count"] == 2
    client.batch_cancel.assert_called_once()
    cancelled_ids = client.batch_cancel.call_args[0][0]
    assert len(cancelled_ids) == 2


@pytest.mark.asyncio
async def test_cancel_no_pending(execution_id: str) -> None:
    """No-op when no pending approvals exist."""
    client = _mock_client([])

    with _patch_client(client):
        result = await cancel_approval_requests_activity(execution_id)

    assert result["cancelled_count"] == 0
    client.batch_cancel.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_api_error(execution_id: str) -> None:
    """API errors return gracefully, not raised."""
    from syntara.workflows.clients.approvals_client import ApprovalsApiClientError

    client = AsyncMock()
    client.list_approvals_by_execution = AsyncMock(
        side_effect=ApprovalsApiClientError("Service unavailable", status_code=503)
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with _patch_client(client):
        result = await cancel_approval_requests_activity(execution_id)

    assert result["cancelled_count"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_cancel_unexpected_error(execution_id: str) -> None:
    """Unexpected errors return gracefully, not raised."""
    client = AsyncMock()
    client.list_approvals_by_execution = AsyncMock(side_effect=RuntimeError("connection lost"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with _patch_client(client):
        result = await cancel_approval_requests_activity(execution_id)

    assert result["cancelled_count"] == 0
    assert "error" in result
