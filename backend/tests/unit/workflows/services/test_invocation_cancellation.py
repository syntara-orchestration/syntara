"""Unit tests for invocation_cancellation helper module."""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.agent_orchestrator.models.request import CancellationResult
from syntara.agent_orchestrator.services.invocation_service import InvocationService
from syntara.workflows.services.invocation_cancellation import (
    cancel_invocations_for_execution,
    find_active_invocations_for_execution,
    linked_invocation_ids,
)


def _make_invocation(
    execution_id: str,
    status: InvocationStatus = InvocationStatus.RUNNING,
) -> Invocation:
    inv = Mock(spec=Invocation)
    inv.id = uuid4()
    inv.status = status
    inv.error_message = None
    inv.completed_at = None
    return inv


def _session_for_lookup(linked_ids: list[str], invocations: list[Invocation]) -> Mock:
    """Session whose first exec() yields the activity-output link, second the rows."""
    link_result = Mock()
    link_result.all.return_value = linked_ids
    invocation_result = Mock()
    invocation_result.all.return_value = invocations

    mock_session = Mock()
    mock_session.exec = AsyncMock(side_effect=[link_result, invocation_result])
    return mock_session


def _mock_service() -> Mock:
    """Stand-in for the InvocationService the caller injects."""
    service = Mock(spec=InvocationService)
    service.cancel_invocation = AsyncMock(return_value=CancellationResult.SUCCESS)
    return service


class TestFindActiveInvocationsForExecution:
    """Lookup of cancellable invocations by execution_id."""

    @pytest.mark.asyncio
    async def test_returns_matching_invocations(self) -> None:
        execution_id = uuid4()
        inv = _make_invocation(str(execution_id))
        mock_session = _session_for_lookup([str(inv.id)], [inv])

        result = await find_active_invocations_for_execution(mock_session, execution_id)

        assert result == [inv]

    @pytest.mark.asyncio
    async def test_returns_empty_when_activity_output_has_no_link(self) -> None:
        """No agentic activity reported an invocation, so nothing is loaded."""
        execution_id = uuid4()
        mock_session = _session_for_lookup([], [])

        result = await find_active_invocations_for_execution(mock_session, execution_id)

        assert result == []
        mock_session.exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_empty_when_linked_rows_are_not_cancellable(self) -> None:
        execution_id = uuid4()
        mock_session = _session_for_lookup([str(uuid4())], [])

        result = await find_active_invocations_for_execution(mock_session, execution_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_malformed_invocation_id_is_ignored(self) -> None:
        """A non-UUID in activity output must not break the cancel path."""
        execution_id = uuid4()
        mock_session = _session_for_lookup(["not-a-uuid", None], [])  # type: ignore[list-item]

        result = await linked_invocation_ids(mock_session, execution_id)

        assert result == []


class TestCancelInvocationsForExecution:
    """Bulk cancel delegates to the InvocationService it is handed."""

    @pytest.mark.asyncio
    async def test_no_active_invocations_returns_empty(self) -> None:
        execution_id = uuid4()
        mock_session = Mock()

        with patch(
            "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await cancel_invocations_for_execution(mock_session, execution_id, _mock_service())

        assert result == []

    @pytest.mark.asyncio
    async def test_cancels_single_invocation_via_injected_service(self) -> None:
        """The caller's service is used as-is; none is constructed here.

        The service carries the Temporal dependency needed to stop the builtin
        workflow running each invocation, so building one locally would silently
        drop that half of the cancel.
        """
        execution_id = uuid4()
        inv = _make_invocation(str(execution_id))
        mock_session = Mock()
        mock_service = _mock_service()

        with patch(
            "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=[inv],
        ):
            result = await cancel_invocations_for_execution(mock_session, execution_id, mock_service)

        assert result == [inv.id]
        mock_service.cancel_invocation.assert_awaited_once_with(inv.id, "Workflow execution cancelled")

    @pytest.mark.asyncio
    async def test_module_does_not_construct_an_invocation_service(self) -> None:
        """The bridge is not a service factory — it never imports one at runtime."""
        import syntara.workflows.services.invocation_cancellation as module

        assert not hasattr(module, "InvocationService")

    @pytest.mark.asyncio
    async def test_cancels_multiple_invocations(self) -> None:
        execution_id = uuid4()
        invocations = [_make_invocation(str(execution_id)) for _ in range(3)]
        mock_session = Mock()
        mock_service = _mock_service()

        with patch(
            "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=invocations,
        ):
            result = await cancel_invocations_for_execution(mock_session, execution_id, mock_service)

        assert result == [inv.id for inv in invocations]
        assert mock_service.cancel_invocation.await_count == 3

    @pytest.mark.asyncio
    async def test_one_failure_does_not_block_others(self) -> None:
        execution_id = uuid4()
        invocations = [_make_invocation(str(execution_id)) for _ in range(2)]
        mock_session = Mock()
        mock_session.rollback = AsyncMock()
        mock_service = _mock_service()
        mock_service.cancel_invocation = AsyncMock(side_effect=[Exception("DB error"), CancellationResult.SUCCESS])

        with patch(
            "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=invocations,
        ):
            result = await cancel_invocations_for_execution(mock_session, execution_id, mock_service)

        assert result == [invocations[1].id]
        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_cancellable_is_not_returned(self) -> None:
        execution_id = uuid4()
        inv = _make_invocation(str(execution_id))
        mock_session = Mock()
        mock_service = _mock_service()
        mock_service.cancel_invocation = AsyncMock(return_value=CancellationResult.NOT_CANCELLABLE)

        with patch(
            "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=[inv],
        ):
            result = await cancel_invocations_for_execution(mock_session, execution_id, mock_service)

        assert result == []

    @pytest.mark.asyncio
    async def test_custom_reason_passed_to_service(self) -> None:
        execution_id = uuid4()
        inv = _make_invocation(str(execution_id))
        mock_session = Mock()
        mock_service = _mock_service()

        with patch(
            "syntara.workflows.services.invocation_cancellation.find_active_invocations_for_execution",
            new_callable=AsyncMock,
            return_value=[inv],
        ):
            await cancel_invocations_for_execution(mock_session, execution_id, mock_service, reason="User requested")

        mock_service.cancel_invocation.assert_awaited_once_with(inv.id, "User requested")
