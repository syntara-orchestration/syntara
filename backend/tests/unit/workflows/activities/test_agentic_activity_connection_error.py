"""Unit tests for agentic activity connection-failure messaging (AGENT-05)."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.clients.agent_orchestrator_client import AgentOrchestratorClientConnectionError
from syntara.workflows.workflow_engine.activities.agentic_activity import execute_agentic_activity

AGENT_SERVICE_UNAVAILABLE_MESSAGE = (
    "The AI Agent service is temporarily unavailable. This is a system issue. "
    "Please try again in a few minutes. If this persists, contact your administrator."
)


async def _fake_inject_runtime_settings(input_config: dict[str, object]) -> None:
    """Inject default timeout like the real helper does."""
    if "timeout" not in input_config:
        input_config["timeout"] = 300


@pytest.fixture
def mock_agent_client() -> Generator[AsyncMock, None, None]:
    """Mock Agent Orchestrator client and activity heartbeat."""
    with (
        patch("temporalio.activity.heartbeat"),
        patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
        patch(
            "syntara.workflows.workflow_engine.activities.agentic_activity._inject_runtime_settings",
            side_effect=_fake_inject_runtime_settings,
        ),
    ):
        mock_instance = AsyncMock()
        mock_instance.invoke_agent_async = AsyncMock(return_value="inv_123456")
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_instance
        yield mock_instance


class TestAgenticActivityConnectionError:
    """Pre-dispatch connection failures must use user-friendly copy."""

    @pytest.mark.asyncio
    async def test_connection_error_uses_user_friendly_message(self, mock_agent_client: AsyncMock) -> None:
        """AgentOrchestratorClientConnectionError surfaces AGENT-05 guidance, not internal service name."""
        mock_agent_client.invoke_agent_async.side_effect = AgentOrchestratorClientConnectionError(
            "Agent Orchestrator unavailable"
        )

        input_config = {
            "prompt": "Test prompt",
            "llm_model_id": "550e8400-e29b-41d4-a716-446655440000",
        }

        with pytest.raises(ApplicationError) as exc_info:
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        assert exc_info.value.message == AGENT_SERVICE_UNAVAILABLE_MESSAGE
        assert exc_info.value.type == "ConnectionError"
        assert "agent orchestrator" not in exc_info.value.message.lower()
        assert "Failed to connect to Agent Orchestrator" not in exc_info.value.message
