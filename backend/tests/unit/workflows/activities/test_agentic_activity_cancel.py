"""Unit tests for cancel_agentic_invocation_activity.

Tests cancelling running agentic invocations when a workflow is cancelled
or a node times out.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.workflows.workflow_engine.activities.agentic_activity import (
    cancel_agentic_invocation_activity,
)


def _make_activity_execution(
    execution_id: str,
    *,
    activity_name: str = "agentic_node_1",
    node_type: str = "agentic",
    status: str = "running",
    output_data: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock ActivityExecution row."""
    row = MagicMock()
    row.execution_id = execution_id
    row.activity_name = activity_name
    row.node_type = node_type
    row.status = status
    row.output_data = output_data
    return row


def _mock_session_with_rows(rows: list[MagicMock]) -> AsyncMock:
    """Build a mock async session that returns the given rows from exec()."""
    mock_result = MagicMock()
    mock_result.all.return_value = rows

    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_result)
    return mock_session


def _patch_get_db(mock_session: AsyncMock):  # noqa: ANN202
    """Patch get_db to yield the given mock session."""

    async def mock_get_db():  # noqa: ANN202
        yield mock_session

    return patch(
        "syntara.core.database.session.get_db",
        mock_get_db,
    )


def _patch_agent_client(mock_client: AsyncMock):  # noqa: ANN202
    """Patch AgentOrchestratorClient constructor to return mock_client."""
    return patch(
        "syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient",
        return_value=mock_client,
    )


def _make_agent_client_mock() -> AsyncMock:
    """Create a mock AgentOrchestratorClient as async context manager."""
    client = AsyncMock()
    client.cancel_invocation = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


class TestCancelAgenticInvocationActivity:
    """Tests for cancel_agentic_invocation_activity."""

    @pytest.mark.asyncio
    async def test_cancel_finds_and_cancels_invocation(self) -> None:
        """Running agentic activity with invocation_id in output_data triggers cancel."""
        execution_id = str(uuid4())
        invocation_id = "inv-abc-123"

        row = _make_activity_execution(
            execution_id,
            output_data={"invocation_id": invocation_id},
        )
        mock_session = _mock_session_with_rows([row])
        mock_client = _make_agent_client_mock()

        with _patch_get_db(mock_session), _patch_agent_client(mock_client):
            result = await cancel_agentic_invocation_activity(execution_id)

        assert result == {"attempted_count": 1}
        mock_client.cancel_invocation.assert_called_once_with(invocation_id, reason="Workflow cancelled")

    @pytest.mark.asyncio
    async def test_cancel_returns_zero_when_no_running_activities(self) -> None:
        """No running activities yields attempted_count=0 and no client call."""
        execution_id = str(uuid4())

        mock_session = _mock_session_with_rows([])
        mock_client = _make_agent_client_mock()

        with _patch_get_db(mock_session), _patch_agent_client(mock_client):
            result = await cancel_agentic_invocation_activity(execution_id)

        assert result == {"attempted_count": 0}
        mock_client.cancel_invocation.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_filters_by_node_id(self) -> None:
        """When node_id is provided, the query includes activity_name filter."""
        execution_id = str(uuid4())
        node_id = "agentic_timeout_node"
        invocation_id = "inv-node-456"

        row = _make_activity_execution(
            execution_id,
            activity_name=node_id,
            output_data={"invocation_id": invocation_id},
        )
        mock_session = _mock_session_with_rows([row])
        mock_client = _make_agent_client_mock()

        with _patch_get_db(mock_session), _patch_agent_client(mock_client):
            result = await cancel_agentic_invocation_activity(execution_id, node_id=node_id, reason="Node timeout")

        assert result == {"attempted_count": 1}
        mock_client.cancel_invocation.assert_called_once_with(invocation_id, reason="Node timeout")

        # Verify the session.exec was called (query was built and executed)
        mock_session.exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_multiple_invocations(self) -> None:
        """Multiple running agentic activities are all cancelled."""
        execution_id = str(uuid4())
        inv_ids = ["inv-1", "inv-2", "inv-3"]

        rows = [
            _make_activity_execution(
                execution_id,
                activity_name=f"node_{i}",
                output_data={"invocation_id": inv_id},
            )
            for i, inv_id in enumerate(inv_ids)
        ]
        mock_session = _mock_session_with_rows(rows)
        mock_client = _make_agent_client_mock()

        with _patch_get_db(mock_session), _patch_agent_client(mock_client):
            result = await cancel_agentic_invocation_activity(execution_id)

        assert result == {"attempted_count": 3}
        assert mock_client.cancel_invocation.call_count == 3
        cancelled_ids = [call.args[0] for call in mock_client.cancel_invocation.call_args_list]
        assert cancelled_ids == inv_ids

    @pytest.mark.asyncio
    async def test_cancel_skips_activities_without_invocation_id(self) -> None:
        """Activities whose output_data lacks invocation_id are skipped."""
        execution_id = str(uuid4())

        rows = [
            _make_activity_execution(execution_id, output_data={"some_key": "value"}),
            _make_activity_execution(execution_id, output_data=None),
            _make_activity_execution(execution_id, output_data={"invocation_id": "inv-only-one"}),
        ]
        mock_session = _mock_session_with_rows(rows)
        mock_client = _make_agent_client_mock()

        with _patch_get_db(mock_session), _patch_agent_client(mock_client):
            result = await cancel_agentic_invocation_activity(execution_id)

        assert result == {"attempted_count": 1}
        mock_client.cancel_invocation.assert_called_once_with("inv-only-one", reason="Workflow cancelled")

    @pytest.mark.asyncio
    async def test_cancel_uses_custom_reason(self) -> None:
        """Custom reason string is forwarded to cancel_invocation."""
        execution_id = str(uuid4())
        custom_reason = "User requested stop"

        row = _make_activity_execution(
            execution_id,
            output_data={"invocation_id": "inv-reason-test"},
        )
        mock_session = _mock_session_with_rows([row])
        mock_client = _make_agent_client_mock()

        with _patch_get_db(mock_session), _patch_agent_client(mock_client):
            result = await cancel_agentic_invocation_activity(execution_id, reason=custom_reason)

        assert result == {"attempted_count": 1}
        mock_client.cancel_invocation.assert_called_once_with("inv-reason-test", reason=custom_reason)
