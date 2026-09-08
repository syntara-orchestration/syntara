"""Unit tests for expire approval activity.

Tests expiring pending approval requests when a decision window times out.
"""

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from syntara.workflows.workflow_engine.activities.approval_activity import (
    _is_approval_for_node,
    expire_approval_requests_activity,
)


@pytest.fixture
def execution_id() -> str:
    """Workflow execution ID."""
    return str(uuid4())


@pytest.fixture
def node_id() -> str:
    """Approval node identifier."""
    return "approval_step_1"


@pytest.fixture
def pending_approvals(execution_id: str, node_id: str) -> list[dict[str, Any]]:
    """Two pending approval requests for the target node."""
    return [
        {"id": str(uuid4()), "approval_node_id": node_id, "status": "pending"},
        {"id": str(uuid4()), "approval_node_id": node_id, "status": "pending"},
    ]


@pytest.mark.asyncio
async def test_expire_success(
    execution_id: str,
    node_id: str,
    pending_approvals: list[dict[str, Any]],
) -> None:
    """Pending approvals for the node are batch-expired."""
    mock_client = AsyncMock()
    mock_client.list_approvals_by_execution = AsyncMock(return_value=pending_approvals)
    mock_client.batch_expire = AsyncMock(return_value={"total_success": 2, "total_failed": 0})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
    ):
        result = await expire_approval_requests_activity(execution_id, node_id)

    assert result["expired_count"] == 2
    mock_client.batch_expire.assert_called_once()
    expired_ids = mock_client.batch_expire.call_args[0][0]
    assert len(expired_ids) == 2


@pytest.mark.asyncio
async def test_expire_no_pending_approvals(execution_id: str, node_id: str) -> None:
    """No-op when there are no pending approvals for the node."""
    mock_client = AsyncMock()
    mock_client.list_approvals_by_execution = AsyncMock(return_value=[])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
    ):
        result = await expire_approval_requests_activity(execution_id, node_id)

    assert result["expired_count"] == 0
    mock_client.batch_expire.assert_not_called()


@pytest.mark.asyncio
async def test_expire_filters_by_node_id(execution_id: str, node_id: str) -> None:
    """Only approvals matching the specific node_id are expired."""
    other_node_approval = {"id": str(uuid4()), "approval_node_id": "other_node", "status": "pending"}
    target_approval = {"id": str(uuid4()), "approval_node_id": node_id, "status": "pending"}

    mock_client = AsyncMock()
    mock_client.list_approvals_by_execution = AsyncMock(return_value=[other_node_approval, target_approval])
    mock_client.batch_expire = AsyncMock(return_value={"total_success": 1, "total_failed": 0})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
    ):
        result = await expire_approval_requests_activity(execution_id, node_id)

    assert result["expired_count"] == 1
    expired_ids = mock_client.batch_expire.call_args[0][0]
    assert len(expired_ids) == 1


@pytest.mark.asyncio
async def test_expire_matches_loop_iteration_suffix(execution_id: str, node_id: str) -> None:
    """Loop-iteration approval_node_id values are expired for the canvas node."""
    loop_approval = {"id": str(uuid4()), "approval_node_id": f"{node_id}_iter_1", "status": "pending"}
    other_approval = {"id": str(uuid4()), "approval_node_id": "other_node_iter_1", "status": "pending"}

    mock_client = AsyncMock()
    mock_client.list_approvals_by_execution = AsyncMock(return_value=[loop_approval, other_approval])
    mock_client.batch_expire = AsyncMock(return_value={"total_success": 1, "total_failed": 0})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
    ):
        result = await expire_approval_requests_activity(execution_id, node_id)

    assert result["expired_count"] == 1
    expired_ids = mock_client.batch_expire.call_args[0][0]
    assert expired_ids == [UUID(loop_approval["id"])]


@pytest.mark.asyncio
async def test_expire_matches_nested_loop_iteration_suffix(execution_id: str, node_id: str) -> None:
    """Nested-loop approval_node_id values are expired for the canvas node."""
    nested_approval = {"id": str(uuid4()), "approval_node_id": f"{node_id}_iter_1_iter_0", "status": "pending"}
    other_approval = {"id": str(uuid4()), "approval_node_id": "other_node_iter_1_iter_0", "status": "pending"}

    mock_client = AsyncMock()
    mock_client.list_approvals_by_execution = AsyncMock(return_value=[nested_approval, other_approval])
    mock_client.batch_expire = AsyncMock(return_value={"total_success": 1, "total_failed": 0})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
    ):
        result = await expire_approval_requests_activity(execution_id, node_id)

    assert result["expired_count"] == 1
    expired_ids = mock_client.batch_expire.call_args[0][0]
    assert expired_ids == [UUID(nested_approval["id"])]


def test_is_approval_for_node_requires_numeric_iter_suffix(node_id: str) -> None:
    """Expire matching uses numeric _iter_N suffixes, including nested loops."""
    assert _is_approval_for_node(node_id, node_id)
    assert _is_approval_for_node(f"{node_id}_iter_0", node_id)
    assert _is_approval_for_node(f"{node_id}_iter_12", node_id)
    assert _is_approval_for_node(f"{node_id}_iter_1_iter_0", node_id)
    assert _is_approval_for_node(node_id, f"{node_id}_iter_0")
    assert not _is_approval_for_node(f"{node_id}_iter_notanumber", node_id)
    assert not _is_approval_for_node("other_node_iter_1", node_id)
    assert not _is_approval_for_node(f"{node_id}_iter_1_extra", node_id)


@pytest.mark.asyncio
async def test_expire_ignores_non_numeric_iter_suffix(execution_id: str, node_id: str) -> None:
    """A non-numeric _iter_ suffix is not treated as a loop-iteration approval."""
    unrelated = {"id": str(uuid4()), "approval_node_id": f"{node_id}_iter_notanumber", "status": "pending"}

    mock_client = AsyncMock()
    mock_client.list_approvals_by_execution = AsyncMock(return_value=[unrelated])
    mock_client.batch_expire = AsyncMock(return_value={"total_success": 0, "total_failed": 0})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
    ):
        result = await expire_approval_requests_activity(execution_id, node_id)

    assert result["expired_count"] == 0
    mock_client.batch_expire.assert_not_called()


@pytest.mark.asyncio
async def test_expire_api_error_returns_gracefully(execution_id: str, node_id: str) -> None:
    """API errors are caught and returned as error info, not raised."""
    from syntara.workflows.clients.approvals_client import ApprovalsApiClientError

    mock_client = AsyncMock()
    mock_client.list_approvals_by_execution = AsyncMock(
        side_effect=ApprovalsApiClientError("Service unavailable", status_code=503)
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
    ):
        result = await expire_approval_requests_activity(execution_id, node_id)

    assert result["expired_count"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_expire_all_pending_when_node_id_none(execution_id: str) -> None:
    """When node_id is omitted, pending approvals across all nodes are expired."""
    approvals = [
        {"id": str(uuid4()), "approval_node_id": "approval_1", "status": "pending"},
        {"id": str(uuid4()), "approval_node_id": "approval_2", "status": "pending"},
    ]

    mock_client = AsyncMock()
    mock_client.list_approvals_by_execution = AsyncMock(return_value=approvals)
    mock_client.batch_expire = AsyncMock(return_value={"total_success": 2, "total_failed": 0})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.AuditEventDispatcher",
        ) as mock_dispatcher,
    ):
        result = await expire_approval_requests_activity(execution_id)

    assert result["expired_count"] == 2
    expired_ids = mock_client.batch_expire.call_args[0][0]
    assert len(expired_ids) == 2
    dispatched_node_ids = {call.args[0].approval_node_id for call in mock_dispatcher.dispatch.call_args_list}
    assert dispatched_node_ids == {"approval_1", "approval_2"}


@pytest.mark.asyncio
async def test_expire_fails_before_mutating_on_malformed_record(execution_id: str) -> None:
    """A record missing approval_node_id fails before batch_expire runs.

    Guards against silently reporting "0 expired" while the mutation actually
    succeeded: validation of the audit-record shape must happen before the
    mutating API call, not after. Uses node_id=None (execution-wide expiry) since
    the per-node filter path would otherwise drop the malformed record before
    it's ever validated.
    """
    malformed_approval = {"id": str(uuid4()), "status": "pending"}  # missing approval_node_id

    mock_client = AsyncMock()
    mock_client.list_approvals_by_execution = AsyncMock(return_value=[malformed_approval])
    mock_client.batch_expire = AsyncMock(return_value={"total_success": 1, "total_failed": 0})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
        return_value=mock_client,
    ):
        result = await expire_approval_requests_activity(execution_id)

    assert result["expired_count"] == 0
    assert "error" in result
    mock_client.batch_expire.assert_not_called()


@pytest.mark.asyncio
async def test_expire_unexpected_error_returns_gracefully(execution_id: str, node_id: str) -> None:
    """Unexpected errors are caught and returned as error info, not raised."""
    mock_client = AsyncMock()
    mock_client.list_approvals_by_execution = AsyncMock(side_effect=RuntimeError("connection lost"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "syntara.workflows.workflow_engine.activities.approval_activity.ApprovalsApiClient",
            return_value=mock_client,
        ),
    ):
        result = await expire_approval_requests_activity(execution_id, node_id)

    assert result["expired_count"] == 0
    assert "error" in result
