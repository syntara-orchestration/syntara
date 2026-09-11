"""Unit tests for InvocationExecutor cancellation race condition fixes."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.exceptions import InvocationCancelledError
from syntara.agent_orchestrator.executor.invocation_executor import InvocationExecutor
from syntara.agent_orchestrator.models import InvocationStatus


class TestInvocationExecutorCancellationRaceCondition:
    """Test race condition fixes in InvocationExecutor."""

    @pytest.mark.asyncio
    async def test_execute_invocation_respects_cancellation_during_execution(self) -> None:
        """Test that invocations cancelled during execution are not marked as completed.

        This is the critical race condition test - ensures that if an invocation is
        cancelled while the orchestration service is executing, the final status
        remains CANCELLED and is not overridden to COMPLETED.

        The fix uses a conditional UPDATE that only succeeds if status != CANCELLED,
        preventing the race where cancellation is overwritten.
        """
        # Arrange
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()

        # Create a mock invocation that starts as RUNNING
        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.prompt = "test prompt"
        mock_invocation.session_id = "test-session"
        mock_invocation.context_data = {}

        # Mock the invocation being cancelled DURING execution
        # First get() call returns RUNNING invocation
        mock_session.get.return_value = mock_invocation

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(MagicMock(model_name="test-model", openai_api_base="https://test.example.com"), None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch("syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService") as mock_orchestration,
            patch.object(executor, "_update_invocation_status", new=AsyncMock()) as mock_update,
            patch.object(
                executor, "_complete_invocation_if_not_cancelled", return_value=False
            ) as mock_conditional_update,
        ):
            # Mock execute as async method
            mock_orchestration.return_value.execute = AsyncMock(return_value={"result": "test response"})

            # Act
            await executor.execute_invocation(invocation_id)

            # Assert
            # 1. Conditional update should have been called and returned False (cancelled)
            mock_conditional_update.assert_called_once()
            call_args = mock_conditional_update.call_args
            assert call_args[0][0] == invocation_id

            # 2. _update_invocation_status should only be called once for RUNNING status
            # It should NOT be called for COMPLETED because the conditional update returned False
            assert mock_update.call_count == 1
            # Verify it was called with RUNNING status
            call_args = mock_update.call_args_list[0]
            assert call_args[0][1] == InvocationStatus.RUNNING  # Second positional arg is status

    @pytest.mark.asyncio
    async def test_execute_invocation_raises_when_running_update_fails(self) -> None:
        """Cancel during file conversion / init makes RUNNING update return False.

        When _update_invocation_status(RUNNING) returns False the invocation was
        cancelled while waiting for file conversions or during init. The executor
        must raise InvocationCancelledError and send the cancellation signal instead
        of proceeding to execute().
        """
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
        mock_invocation.context_data = {}

        mock_session.get.return_value = mock_invocation

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(MagicMock(model_name="test-model", openai_api_base="https://test.example.com"), None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch("syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService") as mock_orchestration,
            patch.object(executor, "_update_invocation_status", return_value=False),
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_cancellation_signal",
                new_callable=AsyncMock,
            ) as mock_cancel_signal,
        ):
            mock_orchestration.return_value.execute = AsyncMock()

            with pytest.raises(InvocationCancelledError):
                await executor.execute_invocation(invocation_id)

            mock_cancel_signal.assert_called_once()
            mock_orchestration.return_value.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_invocation_completes_normally_when_not_cancelled(self) -> None:
        """Test that invocations complete normally when not cancelled."""
        # Arrange
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()

        # Create a mock invocation that starts as RUNNING and stays RUNNING
        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.prompt = "test prompt"
        mock_invocation.session_id = "test-session"
        mock_invocation.context_data = {}

        mock_session.get.return_value = mock_invocation

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(MagicMock(model_name="test-model", openai_api_base="https://test.example.com"), None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch("syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService") as mock_orchestration,
            patch.object(executor, "_update_invocation_status", new=AsyncMock()) as mock_update,
            patch.object(
                executor, "_complete_invocation_if_not_cancelled", return_value=True
            ) as mock_conditional_update,
        ):
            # Mock execute as async method
            mock_orchestration.return_value.execute = AsyncMock(return_value={"result": "test response"})

            # Act
            await executor.execute_invocation(invocation_id)

            # Assert
            # 1. Conditional update should have been called and returned True (not cancelled)
            mock_conditional_update.assert_called_once()
            call_args = mock_conditional_update.call_args
            assert call_args[0][0] == invocation_id

            # 2. _update_invocation_status should only be called once for RUNNING
            # COMPLETED is handled by the conditional update
            assert mock_update.call_count == 1

            # Verify it was called with RUNNING status
            first_call = mock_update.call_args_list[0]
            assert first_call[0][1] == InvocationStatus.RUNNING

    @pytest.mark.asyncio
    async def test_execute_invocation_handles_pre_execution_cancellation(self) -> None:
        """Test that invocations cancelled before execution raise and notify the workflow."""
        # Arrange
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()

        # Create a mock invocation that is already CANCELLED
        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.CANCELLED
        mock_invocation.context_data = {
            "callback_url": "https://syntara:8000/api/v1/executions/abc/activities/step/signal"
        }

        mock_session.get.return_value = mock_invocation

        with (
            patch("syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm") as mock_llm,
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_cancellation_signal",
                new_callable=AsyncMock,
            ) as mock_cancel_signal,
        ):
            with pytest.raises(InvocationCancelledError):
                await executor.execute_invocation(invocation_id)

            # LLM should not be created
            mock_llm.assert_not_called()

            # Cancellation signal should be sent to the workflow
            mock_cancel_signal.assert_called_once()
            call_args = mock_cancel_signal.call_args[0]
            assert call_args[1] == invocation_id

    @pytest.mark.asyncio
    async def test_execute_invocation_handles_invocation_cancelled_error(self) -> None:
        """Test that InvocationCancelledError during execution re-raises after sending signal."""
        # Arrange
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()

        # Create a mock invocation that starts as RUNNING
        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.prompt = "test prompt"
        mock_invocation.session_id = "test-session"
        mock_invocation.context_data = {}

        mock_session.get.return_value = mock_invocation

        # Mock session.exec() to return a result with rowcount for status updates
        mock_exec_result = MagicMock()
        mock_exec_result.rowcount = 1  # Simulate successful status update to RUNNING
        mock_session.exec.return_value = mock_exec_result

        from syntara.agent_orchestrator.exceptions import InvocationCancelledError

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(MagicMock(model_name="test-model", openai_api_base="https://test.example.com"), None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch("syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService") as mock_orchestration,
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_cancellation_signal",
                new_callable=AsyncMock,
            ) as mock_cancel_signal,
        ):
            # Simulate InvocationCancelledError being raised during execution
            mock_orchestration.return_value.execute.side_effect = InvocationCancelledError(
                str(invocation_id), "test phase"
            )

            # Act — should re-raise after sending the cancellation signal
            with pytest.raises(InvocationCancelledError):
                await executor.execute_invocation(invocation_id)

            # Assert
            mock_cancel_signal.assert_called_once()
            assert mock_session.commit.call_count == 1

    @pytest.mark.asyncio
    async def test_conditional_update_atomically_checks_cancellation(self) -> None:
        """Test that conditional update atomically checks cancellation status.

        This test verifies that the conditional UPDATE prevents the race condition
        by checking status != CANCELLED atomically in the database.
        """
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
        mock_invocation.context_data = {}

        mock_session.get.return_value = mock_invocation

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(MagicMock(model_name="test-model", openai_api_base="https://test.example.com"), None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch("syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService") as mock_orchestration,
            patch.object(executor, "_update_invocation_status", new=AsyncMock()) as mock_update,
            patch.object(
                executor, "_complete_invocation_if_not_cancelled", return_value=True
            ) as mock_conditional_update,
        ):
            # Mock execute as async method
            mock_orchestration.return_value.execute = AsyncMock(return_value={"result": "test response"})

            # Act
            await executor.execute_invocation(invocation_id)

            # Assert
            # Conditional update should be called exactly once to atomically check and update
            mock_conditional_update.assert_called_once()

            # Regular update should only be called for RUNNING
            assert mock_update.call_count == 1
            assert mock_update.call_args_list[0][0][1] == InvocationStatus.RUNNING

    @pytest.mark.asyncio
    async def test_fail_invocation_sets_started_at_if_not_already_set(self) -> None:
        """Test that _fail_invocation_if_not_cancelled sets started_at if it's None.

        This handles the case where an invocation fails before execution begins
        (e.g., during LLM configuration), ensuring started_at is always set
        for failed invocations.
        """
        # Arrange
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()

        # Create a mock invocation with started_at = None (not yet started)
        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.CREATED
        mock_invocation.started_at = None  # Key: not yet started

        # Mock session.get to return the invocation
        mock_session.get.return_value = mock_invocation

        # Mock session.exec to return a successful result
        mock_exec_result = MagicMock()
        mock_exec_result.rowcount = 1
        mock_session.exec.return_value = mock_exec_result

        # Act
        before_call = datetime.now(UTC)
        result = await executor._fail_invocation_if_not_cancelled(invocation_id, completed_at=datetime.now(UTC))
        after_call = datetime.now(UTC)

        # Assert
        assert result is True  # Update succeeded

        # Verify that session.exec was called with UPDATE statement
        assert mock_session.exec.call_count == 1
        exec_call = mock_session.exec.call_args[0][0]

        # Verify the statement includes status=FAILED
        assert "status" in str(exec_call)

        # Verify started_at was included in the values and is a recent timestamp
        assert hasattr(exec_call, "_values")
        values = exec_call._values
        # Column keys are not strings, need to check by column name
        started_at_col = next((k for k in values if k.name == "started_at"), None)
        assert started_at_col is not None, "started_at should be in UPDATE values"
        started_at_value = values[started_at_col].effective_value
        assert isinstance(started_at_value, datetime)
        assert before_call <= started_at_value <= after_call, "started_at should be auto-set to current time"

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_fail_invocation_does_not_overwrite_existing_started_at(self) -> None:
        """Test that _fail_invocation_if_not_cancelled preserves existing started_at.

        When an invocation fails after execution has begun (started_at is already set),
        the existing started_at timestamp should be preserved.
        """
        # Arrange
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()

        # Create a mock invocation with started_at already set
        original_started_at = datetime.now(UTC) - timedelta(minutes=5)
        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.started_at = original_started_at  # Key: already started

        # Mock session.get to return the invocation
        mock_session.get.return_value = mock_invocation

        # Mock session.exec to return a successful result
        mock_exec_result = MagicMock()
        mock_exec_result.rowcount = 1
        mock_session.exec.return_value = mock_exec_result

        # Act
        result = await executor._fail_invocation_if_not_cancelled(invocation_id, completed_at=datetime.now(UTC))

        # Assert
        assert result is True  # Update succeeded

        # Verify that session.exec was called
        assert mock_session.exec.call_count == 1
        exec_call = mock_session.exec.call_args[0][0]

        # The key assertion: started_at should NOT be in the fields passed to values()
        # because the invocation already has started_at set
        assert hasattr(exec_call, "_values")
        values = exec_call._values
        # Column keys are not strings, need to check by column name
        started_at_col = next((k for k in values if k.name == "started_at"), None)
        assert started_at_col is None, "started_at should not be overwritten when already set"

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_fail_invocation_respects_explicit_started_at_in_fields(self) -> None:
        """Test that explicitly passed started_at in fields is not overridden.

        If the caller explicitly provides started_at in the fields dict,
        that value should be used even if the invocation's started_at is None.
        """
        # Arrange
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()

        # Create a mock invocation with started_at = None
        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.CREATED
        mock_invocation.started_at = None

        # Mock session.get to return the invocation
        mock_session.get.return_value = mock_invocation

        # Mock session.exec to return a successful result
        mock_exec_result = MagicMock()
        mock_exec_result.rowcount = 1
        mock_session.exec.return_value = mock_exec_result

        # Act - explicitly pass started_at in fields
        explicit_started_at = datetime.now(UTC) - timedelta(hours=1)
        result = await executor._fail_invocation_if_not_cancelled(
            invocation_id, completed_at=datetime.now(UTC), started_at=explicit_started_at
        )

        # Assert
        assert result is True  # Update succeeded

        # Verify that the explicit started_at value was used, not auto-generated
        assert mock_session.exec.call_count == 1
        exec_call = mock_session.exec.call_args[0][0]
        assert hasattr(exec_call, "_values")
        values = exec_call._values
        # Column keys are not strings, need to check by column name
        started_at_col = next((k for k in values if k.name == "started_at"), None)
        assert started_at_col is not None, "started_at should be in UPDATE values"
        assert values[started_at_col].effective_value == explicit_started_at, "Explicit started_at should be preserved"

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancelled_error_sends_cancellation_signal(self) -> None:
        """Test that InvocationCancelledError handler sends a cancellation signal."""
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
        mock_invocation.context_data = {}

        mock_session.get.return_value = mock_invocation

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(MagicMock(model_name="test-model", openai_api_base="https://test.example.com"), None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch("syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService") as mock_orchestration,
            patch.object(executor, "_update_invocation_status", new=AsyncMock()),
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_cancellation_signal",
                new=AsyncMock(),
            ) as mock_signal,
        ):
            mock_orchestration.return_value.execute.side_effect = InvocationCancelledError(
                str(invocation_id), "streaming"
            )

            with pytest.raises(InvocationCancelledError):
                await executor.execute_invocation(invocation_id)

            mock_signal.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pre_start_cancel_propagates_despite_signal_failure(self) -> None:
        """InvocationCancelledError propagates even when send_cancellation_signal raises."""
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()

        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.CANCELLED
        mock_invocation.context_data = {"callback_url": "not-a-url"}

        mock_session.get.return_value = mock_invocation

        with patch(
            "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_cancellation_signal",
            new_callable=AsyncMock,
            side_effect=ValueError("invalid signal URL"),
        ):
            with pytest.raises(InvocationCancelledError):
                await executor.execute_invocation(invocation_id)

    @pytest.mark.asyncio
    async def test_mid_execution_cancel_propagates_despite_signal_failure(self) -> None:
        """InvocationCancelledError propagates even when send_cancellation_signal raises mid-execution."""
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
        mock_invocation.context_data = {"callback_url": "not-a-url"}

        mock_session.get.return_value = mock_invocation

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(MagicMock(model_name="test-model", openai_api_base="https://test.example.com"), None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch("syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService") as mock_orch,
            patch.object(executor, "_update_invocation_status", new=AsyncMock()),
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_cancellation_signal",
                new_callable=AsyncMock,
                side_effect=ValueError("invalid signal URL"),
            ),
        ):
            mock_orch.return_value.execute.side_effect = InvocationCancelledError(str(invocation_id), "streaming")

            with pytest.raises(InvocationCancelledError):
                await executor.execute_invocation(invocation_id)

    @pytest.mark.asyncio
    async def test_generic_error_after_cancel_raises_cancelled(self) -> None:
        """When an error occurs after the DB row is CANCELLED, raise InvocationCancelledError."""
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
        mock_invocation.context_data = {}

        mock_session.get.return_value = mock_invocation

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                return_value=(MagicMock(model_name="test-model", openai_api_base="https://test.example.com"), None),
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.ContextManagerPlanner"),
            patch("syntara.agent_orchestrator.executor.invocation_executor.OrchestrationService") as mock_orch,
            patch.object(executor, "_update_invocation_status", new=AsyncMock()),
            patch.object(executor, "_fail_invocation_if_not_cancelled", return_value=False),
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_cancellation_signal",
                new_callable=AsyncMock,
            ) as mock_cancel_signal,
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_failure_signal",
                new_callable=AsyncMock,
            ) as mock_failure_signal,
        ):
            mock_orch.return_value.execute.side_effect = RuntimeError("LLM config error")

            with pytest.raises(InvocationCancelledError):
                await executor.execute_invocation(invocation_id)

            mock_cancel_signal.assert_awaited_once()
            mock_failure_signal.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_cancel_key_sends_signal_and_raises(self) -> None:
        """_check_cancel_key sends cancellation signal to parent workflow before raising."""
        from pydantic import SecretStr

        from syntara.agent_orchestrator.models import InvocationContextData

        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()
        ctx = InvocationContextData(
            callback_url=SecretStr("https://syntara:8000/api/v1/executions/abc/activities/step/signal")
        )

        mock_client = AsyncMock()
        mock_client.key_exists.return_value = True

        with (
            patch("syntara.agent_orchestrator.executor.invocation_executor.StreamClient") as mock_sc,
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_cancellation_signal",
                new_callable=AsyncMock,
            ) as mock_cancel_signal,
        ):
            mock_sc.return_value.__aenter__.return_value = mock_client
            mock_sc.return_value.__aexit__.return_value = None

            with pytest.raises(InvocationCancelledError):
                await executor._check_cancel_key(invocation_id, ctx)

            mock_cancel_signal.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_check_cancel_key_db_fallback_on_redis_error(self) -> None:
        """_check_cancel_key falls back to DB when Redis errors and detects cancellation."""
        from contextlib import asynccontextmanager

        from redis.exceptions import ConnectionError as RedisConnectionError

        from syntara.agent_orchestrator.models import InvocationContextData

        mock_session = AsyncMock()
        mock_invocation = MagicMock()
        mock_invocation.status = InvocationStatus.CANCELLED
        mock_session.get.return_value = mock_invocation

        @asynccontextmanager
        async def mock_session_ctx() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        executor = InvocationExecutor(session_factory=mock_session_factory)
        invocation_id = uuid4()
        ctx = InvocationContextData()

        mock_client = AsyncMock()
        mock_client.key_exists.side_effect = RedisConnectionError("Redis down")

        with (
            patch("syntara.agent_orchestrator.executor.invocation_executor.StreamClient") as mock_sc,
            patch.object(executor, "get_async_session_context", return_value=mock_session_ctx()),
        ):
            mock_sc.return_value.__aenter__.return_value = mock_client
            mock_sc.return_value.__aexit__.return_value = None

            with pytest.raises(InvocationCancelledError):
                await executor._check_cancel_key(invocation_id, ctx)

    @pytest.mark.asyncio
    async def test_init_orchestration_cancel_raises_instead_of_returning_none(self) -> None:
        """LLM config failure after cancel raises InvocationCancelledError, not return None."""
        from syntara.agent_orchestrator.exceptions import LLMConfigurationError

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
        mock_invocation.context_data = {}
        mock_invocation.project_id = None

        mock_session.get.return_value = mock_invocation

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
                side_effect=LLMConfigurationError("No API key"),
            ),
            patch.object(executor, "_update_invocation_status", return_value=False),
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_cancellation_signal",
                new_callable=AsyncMock,
            ) as mock_cancel_signal,
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.WorkflowSignalClient.send_failure_signal",
                new_callable=AsyncMock,
            ) as mock_failure_signal,
        ):
            with pytest.raises(InvocationCancelledError):
                await executor.execute_invocation(invocation_id)

            mock_cancel_signal.assert_awaited_once()
            mock_failure_signal.assert_not_called()
