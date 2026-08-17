"""Contract tests for agentic activity integration.

These tests define the expected behavior of agentic activities:
- Agent Orchestrator invocation and response handling
- Parameter mapping from workflow config to Agent Orchestrator
- Error handling for unavailable Agent Orchestrator
"""

import asyncio
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.agentic_activity import execute_agentic_activity
from tests.fixtures.temporal import CompleteAsyncError


def create_mock_client_response(**kwargs: object) -> dict[str, Any]:
    """Create a standard mock response from Agent Orchestrator."""
    return {
        "id": "inv_123456",
        "status": "completed",
        "result": {"answer": "42", "sources": ["web"]},
        "error_message": None,
        "created_at": "2025-10-31T00:00:00Z",
        "updated_at": "2025-10-31T00:00:01Z",
        "started_at": "2025-10-31T00:00:00Z",
        "completed_at": "2025-10-31T00:00:01Z",
        "prompt": kwargs.get("prompt", "Test prompt"),
        "session_id": "test-session",
        "created_by": "test-user",
        "updated_by": None,
        "checkpoint_data": None,
        "labels": {},
    }


async def _fake_inject_runtime_settings(input_config: dict[str, Any]) -> None:
    """Inject default timeout like the real function does."""
    if "timeout" not in input_config:
        input_config["timeout"] = 300


@pytest.fixture(autouse=True)
def mock_agent_client() -> Generator[AsyncMock, None, None]:
    """Auto-mock Agent Orchestrator client for all tests."""
    with (
        patch("temporalio.activity.heartbeat"),
        patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
        patch(
            "syntara.workflows.workflow_engine.activities.agentic_activity._inject_runtime_settings",
            side_effect=_fake_inject_runtime_settings,
        ),
    ):
        # Create mock instance
        mock_instance = AsyncMock()
        # New async pattern: invoke_agent_async returns invocation_id immediately
        mock_instance.invoke_agent_async = AsyncMock(return_value="inv_123456")
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)

        # Make the class return our mock instance
        mock_cls.return_value = mock_instance

        yield mock_instance


class TestAgenticActivityExecution:
    """Test agentic activity execution and Agent Orchestrator integration."""

    @pytest.mark.asyncio
    async def test_invokes_agent_orchestrator(self, mock_agent_client) -> None:
        """Test that agentic activity invokes Agent Orchestrator asynchronously."""
        input_config = {
            "prompt": "Research and calculate the answer",
            "agent": "syntara-agent://default",
            "llm_model_id": "550e8400-e29b-41d4-a716-446655440000",
        }

        with pytest.raises(CompleteAsyncError):
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        # Verify Agent Orchestrator was called asynchronously
        mock_agent_client.invoke_agent_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_parameter_mapping_to_agent_orchestrator(self, mock_agent_client) -> None:
        """Test that parameters are correctly mapped from config to Agent Orchestrator."""
        input_config = {
            "prompt": "Research and calculate the answer",
            "agent": "syntara-agent://default",
            "llm_model_id": "550e8400-e29b-41d4-a716-446655440000",
        }

        with pytest.raises(CompleteAsyncError):
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        # Verify invoke_agent_async was called with correct parameters
        call_args = mock_agent_client.invoke_agent_async.call_args

        # Check agent
        assert call_args.kwargs["agent"] == "syntara-agent://default"

        # Check llm_model_id is forwarded in metadata
        assert call_args.kwargs["metadata"]["llm_model_id"] == "550e8400-e29b-41d4-a716-446655440000"

        # Check prompt
        assert call_args.kwargs["prompt"] == "Research and calculate the answer"

    @pytest.mark.asyncio
    async def test_invokes_agent_and_gets_result(self, mock_agent_client) -> None:
        """Test that activity invokes agent async and returns metadata."""
        input_config = {
            "prompt": "Research and calculate the answer",
            "agent": "syntara-agent://default",
            "llm_model_id": "550e8400-e29b-41d4-a716-446655440000",
        }

        with pytest.raises(CompleteAsyncError):
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        # Verify invoke_agent_async was called
        mock_agent_client.invoke_agent_async.assert_called()


class TestAgenticActivityErrorHandling:
    """Test error handling for agentic activities."""

    @pytest.mark.asyncio
    async def test_handles_agent_orchestrator_unavailable(self, mock_agent_client) -> None:
        """Test error handling when Agent Orchestrator is unavailable."""
        from syntara.workflows.clients.agent_orchestrator_client import AgentOrchestratorClientConnectionError

        mock_agent_client.invoke_agent_async.side_effect = AgentOrchestratorClientConnectionError(
            "Agent Orchestrator unavailable"
        )

        input_config = {
            "prompt": "Test prompt",
            "llm_model_id": "550e8400-e29b-41d4-a716-446655440000",
        }

        with pytest.raises(ApplicationError) as exc_info:
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))
        error_message = str(exc_info.value)
        assert "temporarily unavailable" in error_message.lower()
        assert "try again" in error_message.lower()
        assert "agent orchestrator" not in error_message.lower()
        assert "Failed to connect to Agent Orchestrator" not in error_message

    @pytest.mark.asyncio
    async def test_handles_agent_orchestrator_timeout(self, mock_agent_client) -> None:
        """Test timeout handling for Agent Orchestrator invocations."""
        from syntara.workflows.clients.agent_orchestrator_client import AgentOrchestratorClientError, ErrorCode

        mock_agent_client.invoke_agent_async.side_effect = AgentOrchestratorClientError(
            "Invocation timed out", code=ErrorCode.TIMEOUT
        )

        input_config = {
            "prompt": "Test prompt",
            "llm_model_id": "550e8400-e29b-41d4-a716-446655440000",
        }

        with pytest.raises(ApplicationError):
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

    @pytest.mark.asyncio
    async def test_handles_agent_orchestrator_error_response(self, mock_agent_client) -> None:
        """Test that async invocation succeeds even if agent will fail later."""
        mock_agent_client.invoke_agent_async.return_value = "inv_error"

        input_config = {
            "prompt": "Test prompt",
            "llm_model_id": "550e8400-e29b-41d4-a716-446655440000",
        }

        with pytest.raises(CompleteAsyncError):
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        # Activity invoked agent successfully (raise_complete_async was called)
        mock_agent_client.invoke_agent_async.assert_called_once()


class TestAgenticActivityEdgeCases:
    """Test edge cases and input validation."""

    @pytest.mark.asyncio
    async def test_rejects_empty_prompt(self) -> None:
        """Test that empty prompts are rejected."""
        input_config = {
            "prompt": "",
            "llm_model_id": "550e8400-e29b-41d4-a716-446655440000",
        }

        with pytest.raises(ApplicationError) as exc_info:
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))
        assert exc_info.value.type == "ConfigError"

    @pytest.mark.asyncio
    async def test_rejects_whitespace_only_prompt(self) -> None:
        """Test that whitespace-only prompts are rejected."""
        input_config = {
            "prompt": "   \t\n  ",
            "llm_model_id": "550e8400-e29b-41d4-a716-446655440000",
        }

        with pytest.raises(ApplicationError) as exc_info:
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))
        assert exc_info.value.type == "ConfigError"


class TestAgenticActivityTimeoutConfiguration:
    """Test timeout configuration for agentic activities."""

    @pytest.mark.asyncio
    async def test_uses_default_timeout_when_not_specified(self, mock_agent_client) -> None:
        """Test that default timeout (300s) is used when not specified in config."""
        input_config = {
            "prompt": "Test prompt",
            "llm_model_id": "550e8400-e29b-41d4-a716-446655440000",
        }

        with pytest.raises(CompleteAsyncError):
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        mock_agent_client.invoke_agent_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_custom_timeout_when_specified(self, mock_agent_client) -> None:
        """Test that custom timeout is accepted."""
        input_config = {
            "prompt": "Test prompt",
            "llm_model_id": "550e8400-e29b-41d4-a716-446655440000",
            "timeout": 600,
        }

        with pytest.raises(CompleteAsyncError):
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        mock_agent_client.invoke_agent_async.assert_called_once()


class TestAgenticActivityInputEdgeCases:
    """Test edge cases in input handling."""

    @pytest.mark.asyncio
    async def test_handles_empty_input(self) -> None:
        """Test that activity handles config with just required fields."""
        input_config = {
            "prompt": "Static prompt with no variables",
            "llm_model_id": "550e8400-e29b-41d4-a716-446655440000",
        }

        with pytest.raises(CompleteAsyncError):
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

    @pytest.mark.asyncio
    async def test_concurrent_invocations_use_separate_clients(self) -> None:
        """Test that concurrent invocations can execute without interference."""
        input_config = {
            "prompt": "Test prompt",
            "llm_model_id": "550e8400-e29b-41d4-a716-446655440000",
        }

        # All three invocations raise CompleteAsyncError on success
        results = await asyncio.gather(
            execute_agentic_activity(input_config, None, project_id=str(uuid4())),
            execute_agentic_activity(input_config, None, project_id=str(uuid4())),
            execute_agentic_activity(input_config, None, project_id=str(uuid4())),
            return_exceptions=True,
        )

        assert len(results) == 3
        assert all(isinstance(r, CompleteAsyncError) for r in results)
