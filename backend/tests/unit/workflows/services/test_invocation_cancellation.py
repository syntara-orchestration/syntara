"""Unit tests for invocation_cancellation helper module."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.workflows.services.invocation_cancellation import (
    cancel_invocations_for_execution,
    find_active_invocations_for_execution,
)


def _make_invocation(
    execution_id: str,
    status: InvocationStatus = InvocationStatus.RUNNING,
) -> Invocation:
    inv = Mock(spec=Invocation)
    inv.id = uuid4()
    inv.status = status
    inv.context_data = {"execution_id": execution_id}
    inv.error_message = None
    inv.completed_at = None
    return inv


class TestFindActiveInvocationsForExecution:
    @pytest.mark.asyncio
    async def test_returns_matching_invocations(self) -> None:
        execution_id = uuid4()
        inv = _make_invocation(str(execution_id))
        mock_result = Mock()
        mock_result.all.return_value = [inv]
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)

        result = await find_active_invocations_for_execution(mock_session, execution_id)

        assert result == [inv]
        mock_session.exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_match(self) -> None:
        execution_id = uuid4()
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)

        result = await find_active_invocations_for_execution(mock_session, execution_id)

        assert result == []


class TestCancelInvocationsForExecution:
    @pytest.mark.asyncio
    async def test_no_active_invocations_returns_zero(self) -> None:
        execution_id = uuid4()
        mock_session = Mock()

        with patch(
            "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await cancel_invocations_for_execution(mock_session, execution_id)

        assert result == 0

    @pytest.mark.asyncio
    async def test_cancels_single_invocation(self) -> None:
        execution_id = uuid4()
        inv = _make_invocation(str(execution_id))
        mock_session = Mock()
        mock_session.commit = AsyncMock()

        with patch(
            "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=[inv],
        ):
            result = await cancel_invocations_for_execution(mock_session, execution_id)

        assert result == 1
        assert inv.status == InvocationStatus.CANCELLED
        assert "Workflow cancelled" in inv.error_message
        assert inv.completed_at is not None
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancels_multiple_invocations(self) -> None:
        execution_id = uuid4()
        invocations = [_make_invocation(str(execution_id)) for _ in range(3)]
        mock_session = Mock()
        mock_session.commit = AsyncMock()

        with patch(
            "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=invocations,
        ):
            result = await cancel_invocations_for_execution(mock_session, execution_id)

        assert result == 3
        for inv in invocations:
            assert inv.status == InvocationStatus.CANCELLED
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commit_failure_returns_zero(self) -> None:
        execution_id = uuid4()
        inv = _make_invocation(str(execution_id))
        mock_session = Mock()
        mock_session.commit = AsyncMock(side_effect=Exception("DB error"))

        with patch(
            "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=[inv],
        ):
            result = await cancel_invocations_for_execution(mock_session, execution_id)

        assert result == 0

    @pytest.mark.asyncio
    async def test_custom_reason_in_error_message(self) -> None:
        execution_id = uuid4()
        inv = _make_invocation(str(execution_id))
        mock_session = Mock()
        mock_session.commit = AsyncMock()

        with patch(
            "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=[inv],
        ):
            await cancel_invocations_for_execution(
                mock_session, execution_id, reason="User requested"
            )

        assert inv.error_message == "Workflow cancelled: User requested"
