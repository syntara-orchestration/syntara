"""Unit tests for approval activity.

Tests approval request creation via the Approvals API client.
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.clients.approvals_client import ApprovalsApiClientError
from syntara.workflows.workflow_engine.activities.approval_activity import (
    ApprovalActivityError,
    create_approval_request_activity,
)
from tests.fixtures.temporal import CompleteAsyncError


@pytest.fixture(autouse=True)
def _mock_heartbeat() -> Generator[None, None, None]:
    """Auto-mock activity.heartbeat() so tests can run outside a Temporal worker."""
    with patch("temporalio.activity.heartbeat"):
        yield


@pytest.fixture
def execution_id() -> str:
    """Workflow execution ID."""
    return str(uuid4())


@pytest.fixture
def test_project_id() -> str:
    """Project ID for approval requests."""
    return str(uuid4())


@pytest.fixture
def approval_node_id() -> str:
    """Approval node identifier."""
    return "review_deployment"


@pytest.fixture
def next_step_approved() -> dict[str, Any]:
    """Next step activity summary for the approved path."""
    return {"id": "deploy", "name": "Deploy to Production", "type": "task"}


@pytest.fixture
def workflow_context() -> dict[str, Any]:
    """Workflow context for approval request."""
    return {
        "workflow_id": str(uuid4()),
        "workflow_name": "Production Deployment",
        "inputs": {"target": "production", "version": "2.1.0"},
        "previous_step": {
            "id": "security_scan",
            "name": "Security Scan",
            "type": "task",
            "output": {"vulnerabilities_found": 0},
        },
    }


@pytest.fixture
def mock_approval_response(execution_id: str) -> dict[str, Any]:
    """Build a mock approval response dict from the API."""
    return {
        "id": str(uuid4()),
        "execution_id": execution_id,
        "approval_node_id": "review_deployment",
        "name": "Approve deployment",
        "status": "pending",
        "timeout_at": None,
        "next_step_approved": {"id": "deploy", "name": "Deploy to Production", "type": "task"},
        "next_step_rejected": None,
        "workflow_context": {
            "workflow_id": str(uuid4()),
            "workflow_name": "Production Deployment",
            "inputs": {"target": "production"},
            "previous_step": None,
        },
        "decided_by": None,
        "decided_at": None,
        "decision_notes": None,
        "created_at": "2026-04-10T12:00:00Z",
        "updated_at": "2026-04-10T12:00:00Z",
    }


@pytest.mark.asyncio
async def test_create_approval_request_success(
    execution_id: str,
    approval_node_id: str,
    next_step_approved: dict[str, Any],
    workflow_context: dict[str, Any],
    mock_approval_response: dict[str, Any],
    test_project_id: str,
) -> None:
    """Test successful approval request creation via API."""
    mock_client = AsyncMock()
    mock_client.create_approval = AsyncMock(return_value=mock_approval_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
        pytest.raises(CompleteAsyncError),
    ):
        await create_approval_request_activity(
            execution_id=execution_id,
            approval_node_id=approval_node_id,
            name="Approve deployment",
            next_step_approved=next_step_approved,
            workflow_context=workflow_context,
            project_id=test_project_id,
        )

    # Verify the request payload passed to the client
    mock_client.create_approval.assert_called_once()
    request_data = mock_client.create_approval.call_args[0][0]
    assert request_data["execution_id"] == execution_id
    assert request_data["approval_node_id"] == approval_node_id
    assert request_data["name"] == "Approve deployment"
    assert request_data["next_step_approved"]["id"] == "deploy"
    assert request_data["workflow_context"]["workflow_name"] == "Production Deployment"


@pytest.mark.asyncio
async def test_create_approval_request_with_timeout(
    execution_id: str,
    approval_node_id: str,
    next_step_approved: dict[str, Any],
    workflow_context: dict[str, Any],
    mock_approval_response: dict[str, Any],
    test_project_id: str,
) -> None:
    """Test approval request with timeout_at."""
    mock_client = AsyncMock()
    mock_client.create_approval = AsyncMock(return_value=mock_approval_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    timeout_at = "2026-04-10T12:00:00+00:00"

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
        pytest.raises(CompleteAsyncError),
    ):
        await create_approval_request_activity(
            execution_id=execution_id,
            approval_node_id=approval_node_id,
            name="Approve deployment",
            next_step_approved=next_step_approved,
            workflow_context=workflow_context,
            timeout_at=timeout_at,
            project_id=test_project_id,
        )

    request_data = mock_client.create_approval.call_args[0][0]
    assert request_data["timeout_at"] == timeout_at


@pytest.mark.asyncio
async def test_create_approval_request_with_rejected_path(
    execution_id: str,
    approval_node_id: str,
    next_step_approved: dict[str, Any],
    workflow_context: dict[str, Any],
    mock_approval_response: dict[str, Any],
    test_project_id: str,
) -> None:
    """Test approval request with rejected path."""
    next_step_rejected = {"id": "rollback", "name": "Rollback", "type": "task"}

    mock_client = AsyncMock()
    mock_client.create_approval = AsyncMock(return_value=mock_approval_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
        pytest.raises(CompleteAsyncError),
    ):
        await create_approval_request_activity(
            execution_id=execution_id,
            approval_node_id=approval_node_id,
            name="Approve deployment",
            next_step_approved=next_step_approved,
            workflow_context=workflow_context,
            next_step_rejected=next_step_rejected,
            project_id=test_project_id,
        )

    request_data = mock_client.create_approval.call_args[0][0]
    assert request_data["next_step_rejected"] is not None
    assert request_data["next_step_rejected"]["id"] == "rollback"


@pytest.mark.asyncio
async def test_create_approval_request_api_error(
    execution_id: str,
    approval_node_id: str,
    next_step_approved: dict[str, Any],
    workflow_context: dict[str, Any],
    test_project_id: str,
) -> None:
    """Test that API errors are wrapped in ApprovalActivityError."""
    mock_client = AsyncMock()
    mock_client.create_approval = AsyncMock(side_effect=ApprovalsApiClientError("Connection refused", status_code=500))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
        pytest.raises(ApprovalActivityError, match="Connection refused"),
    ):
        await create_approval_request_activity(
            execution_id=execution_id,
            approval_node_id=approval_node_id,
            name="Approve deployment",
            next_step_approved=next_step_approved,
            workflow_context=workflow_context,
            project_id=test_project_id,
        )


@pytest.mark.asyncio
async def test_create_approval_request_unexpected_error(
    execution_id: str,
    approval_node_id: str,
    next_step_approved: dict[str, Any],
    workflow_context: dict[str, Any],
    test_project_id: str,
) -> None:
    """Test that unexpected errors are wrapped in ApprovalActivityError."""
    mock_client = AsyncMock()
    mock_client.create_approval = AsyncMock(side_effect=RuntimeError("Database connection lost"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
        pytest.raises(ApprovalActivityError, match="Unexpected error creating approval request"),
    ):
        await create_approval_request_activity(
            execution_id=execution_id,
            approval_node_id=approval_node_id,
            name="Approve deployment",
            next_step_approved=next_step_approved,
            workflow_context=workflow_context,
            project_id=test_project_id,
        )


@pytest.mark.asyncio
async def test_create_approval_request_missing_project_id(
    execution_id: str,
    approval_node_id: str,
    next_step_approved: dict[str, Any],
    workflow_context: dict[str, Any],
) -> None:
    """Test that empty project_id raises ApplicationError."""
    with pytest.raises(ApplicationError) as exc_info:
        await create_approval_request_activity(
            execution_id=execution_id,
            approval_node_id=approval_node_id,
            name="Approve deployment",
            next_step_approved=next_step_approved,
            workflow_context=workflow_context,
            project_id="",
        )
    assert exc_info.value.type == "ConfigError"
