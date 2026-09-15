"""Unit tests for invocation_cancellation helper module."""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.agent_orchestrator.models.request import CancellationResult
from syntara.core.models import User
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


def _mock_user() -> User:
    return Mock(spec=User)


class TestFindActiveInvocationsForExecution:
    """Lookup of cancellable invocations by execution_id."""

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
    """Bulk cancel delegates to InvocationService."""

    @pytest.mark.asyncio
    async def test_no_active_invocations_returns_zero(self) -> None:
        execution_id = uuid4()
        mock_session = Mock()

        with patch(
            "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await cancel_invocations_for_execution(mock_session, _mock_user(), execution_id)

        assert result == 0

    @pytest.mark.asyncio
    async def test_cancels_single_invocation_via_service(self) -> None:
        execution_id = uuid4()
        inv = _make_invocation(str(execution_id))
        mock_session = Mock()
        mock_service = Mock()
        mock_service.cancel_invocation = AsyncMock(return_value=CancellationResult.SUCCESS)

        with (
            patch(
                "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
                new_callable=AsyncMock,
                return_value=[inv],
            ),
            patch(
                "syntara.workflows.services.invocation_cancellation.InvocationService",
                return_value=mock_service,
            ),
        ):
            result = await cancel_invocations_for_execution(mock_session, _mock_user(), execution_id)

        assert result == 1
        mock_service.cancel_invocation.assert_awaited_once_with(inv.id, "Workflow execution cancelled")

    @pytest.mark.asyncio
    async def test_cancels_multiple_invocations(self) -> None:
        execution_id = uuid4()
        invocations = [_make_invocation(str(execution_id)) for _ in range(3)]
        mock_session = Mock()
        mock_service = Mock()
        mock_service.cancel_invocation = AsyncMock(return_value=CancellationResult.SUCCESS)

        with (
            patch(
                "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
                new_callable=AsyncMock,
                return_value=invocations,
            ),
            patch(
                "syntara.workflows.services.invocation_cancellation.InvocationService",
                return_value=mock_service,
            ),
        ):
            result = await cancel_invocations_for_execution(mock_session, _mock_user(), execution_id)

        assert result == 3
        assert mock_service.cancel_invocation.await_count == 3

    @pytest.mark.asyncio
    async def test_one_failure_does_not_block_others(self) -> None:
        execution_id = uuid4()
        invocations = [_make_invocation(str(execution_id)) for _ in range(2)]
        mock_session = Mock()
        mock_session.rollback = AsyncMock()
        mock_service = Mock()
        mock_service.cancel_invocation = AsyncMock(side_effect=[Exception("DB error"), CancellationResult.SUCCESS])

        with (
            patch(
                "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
                new_callable=AsyncMock,
                return_value=invocations,
            ),
            patch(
                "syntara.workflows.services.invocation_cancellation.InvocationService",
                return_value=mock_service,
            ),
        ):
            result = await cancel_invocations_for_execution(mock_session, _mock_user(), execution_id)

        assert result == 1
        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_cancellable_is_not_counted(self) -> None:
        execution_id = uuid4()
        inv = _make_invocation(str(execution_id))
        mock_session = Mock()
        mock_service = Mock()
        mock_service.cancel_invocation = AsyncMock(return_value=CancellationResult.NOT_CANCELLABLE)

        with (
            patch(
                "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
                new_callable=AsyncMock,
                return_value=[inv],
            ),
            patch(
                "syntara.workflows.services.invocation_cancellation.InvocationService",
                return_value=mock_service,
            ),
        ):
            result = await cancel_invocations_for_execution(mock_session, _mock_user(), execution_id)

        assert result == 0

    @pytest.mark.asyncio
    async def test_custom_reason_passed_to_service(self) -> None:
        execution_id = uuid4()
        inv = _make_invocation(str(execution_id))
        mock_session = Mock()
        mock_service = Mock()
        mock_service.cancel_invocation = AsyncMock(return_value=CancellationResult.SUCCESS)

        with (
            patch(
                "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
                new_callable=AsyncMock,
                return_value=[inv],
            ),
            patch(
                "syntara.workflows.services.invocation_cancellation.InvocationService",
                return_value=mock_service,
            ),
        ):
            await cancel_invocations_for_execution(mock_session, _mock_user(), execution_id, reason="User requested")

        mock_service.cancel_invocation.assert_awaited_once_with(inv.id, "User requested")
