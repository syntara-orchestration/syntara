"""Unit tests for InvocationExecutor timeout enforcement."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.executor.invocation_executor import InvocationExecutor
from syntara.agent_orchestrator.models import InvocationStatus


class TestInvocationExecutorTimeout:
    """Test timeout enforcement in InvocationExecutor."""

    @pytest.mark.asyncio
    async def test_timeout_enforced_when_set(self) -> None:
        """Test asyncio.wait_for wraps execute when timeout_seconds is set."""
        # Arrange
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()

        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.prompt = "test prompt"
        mock_invocation.session_id = "test-session"
        mock_invocation.context_data = {"timeout_seconds": 30}

        mock_session.get.return_value = mock_invocation

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(MagicMock(model_name="test-model", openai_api_base="https://test.example.com"), None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch("syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService") as mock_orchestration,
            patch.object(executor, "_update_invocation_status", new=AsyncMock()),
            patch.object(executor, "_fail_invocation_if_not_cancelled", return_value=True) as mock_fail,
            patch("syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient") as mock_signal,
            patch("asyncio.wait_for", side_effect=TimeoutError) as mock_wait_for,
        ):
            mock_orchestration.return_value.execute = AsyncMock()
            mock_signal.send_failure_signal = AsyncMock()

            # Act
            await executor.execute_invocation(invocation_id)

            # Assert - wait_for was called (timeout enforced)
            mock_wait_for.assert_called_once()

            # Assert - failure handler called with error_message containing timeout text
            mock_fail.assert_called_once()
            call_kwargs = mock_fail.call_args[1]
            assert "did not respond in time" in call_kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_no_timeout_when_not_set(self) -> None:
        """Test that asyncio.wait_for is NOT called when timeout_seconds is None."""
        # Arrange
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()

        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.prompt = "test prompt"
        mock_invocation.session_id = "test-session"
        mock_invocation.context_data = {}  # No timeout_seconds

        mock_session.get.return_value = mock_invocation

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(MagicMock(model_name="test-model", openai_api_base="https://test.example.com"), None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch("syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService") as mock_orchestration,
            patch.object(executor, "_update_invocation_status", new=AsyncMock()),
            patch.object(executor, "_complete_invocation_if_not_cancelled", return_value=True),
            patch("asyncio.wait_for") as mock_wait_for,
        ):
            mock_orchestration.return_value.execute = AsyncMock(return_value={"result": "test response"})

            # Act
            await executor.execute_invocation(invocation_id)

            # Assert - wait_for should NOT have been called
            mock_wait_for.assert_not_called()

    @pytest.mark.asyncio
    async def test_timeout_sends_failure_signal(self) -> None:
        """Test that WorkflowSignalClient.send_failure_signal is called on timeout."""
        # Arrange
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()

        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.prompt = "test prompt"
        mock_invocation.session_id = "test-session"
        mock_invocation.context_data = {"timeout_seconds": 10, "callback_url": "https://example.com/callback"}

        mock_session.get.return_value = mock_invocation

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(MagicMock(model_name="test-model", openai_api_base="https://test.example.com"), None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch("syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService") as mock_orchestration,
            patch.object(executor, "_update_invocation_status", new=AsyncMock()),
            patch.object(executor, "_fail_invocation_if_not_cancelled", return_value=True),
            patch("syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient") as mock_signal_cls,
            patch("asyncio.wait_for", side_effect=TimeoutError),
        ):
            mock_orchestration.return_value.execute = AsyncMock()
            mock_signal_cls.send_failure_signal = AsyncMock()

            # Act
            await executor.execute_invocation(invocation_id)

            # Assert - failure signal sent
            mock_signal_cls.send_failure_signal.assert_called_once()
            call_args = mock_signal_cls.send_failure_signal.call_args
            assert call_args[0][1] == invocation_id  # invocation_id arg

    @pytest.mark.asyncio
    async def test_timeout_records_metrics_with_error_status(self) -> None:
        """Test that _record_invocation_metrics is called with status='error' on timeout."""
        # Arrange
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()

        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.prompt = "test prompt"
        mock_invocation.session_id = "test-session"
        mock_invocation.context_data = {"timeout_seconds": 5}

        mock_session.get.return_value = mock_invocation

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(MagicMock(model_name="test-model", openai_api_base="https://test.example.com"), None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch("syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService") as mock_orchestration,
            patch.object(executor, "_update_invocation_status", new=AsyncMock()),
            patch.object(executor, "_fail_invocation_if_not_cancelled", return_value=True),
            patch("syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient") as mock_signal,
            patch("asyncio.wait_for", side_effect=TimeoutError),
            patch.object(executor, "_record_invocation_metrics") as mock_metrics,
        ):
            mock_orchestration.return_value.execute = AsyncMock()
            mock_signal.send_failure_signal = AsyncMock()

            # Act
            await executor.execute_invocation(invocation_id)

            # Assert - metrics recorded with status="error"
            mock_metrics.assert_called_once()
            call_kwargs = mock_metrics.call_args[1]
            assert call_kwargs["status"] == "error"
