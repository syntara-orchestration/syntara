"""Tests for agentic activity runtime settings injection."""

from collections.abc import Generator
from unittest.mock import patch
from uuid import uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.agentic_activity import (
    _build_agent_metadata,
    _inject_runtime_settings,
    execute_agentic_activity,
)
from syntara.workflows.workflow_engine.models import AgenticExecutorParameters


@pytest.fixture(autouse=True)
def _mock_heartbeat() -> Generator[None, None, None]:
    """Auto-mock activity.heartbeat() so tests can run outside a Temporal worker."""
    with patch("temporalio.activity.heartbeat"):
        yield


class TestInjectRuntimeSettings:
    """Tests for _inject_runtime_settings helper."""

    @pytest.mark.asyncio
    async def test_injects_timeout_when_missing(self) -> None:
        config: dict[str, object] = {"prompt": "test"}
        await _inject_runtime_settings(config)
        assert "timeout" in config
        assert isinstance(config["timeout"], int)

    @pytest.mark.asyncio
    async def test_preserves_explicit_timeout(self) -> None:
        config: dict[str, object] = {"prompt": "test", "timeout": 42}
        await _inject_runtime_settings(config)
        assert config["timeout"] == 42

    @pytest.mark.asyncio
    async def test_rejects_prompt_exceeding_max_length(self) -> None:
        prompt_len = 200000
        config: dict[str, object] = {"prompt": "x" * prompt_len}
        with pytest.raises(ValueError, match="exceeds the limit") as exc_info:
            await _inject_runtime_settings(config)
        message = str(exc_info.value)
        assert f"The AI Agent prompt is {prompt_len} characters" in message
        assert "Shorten the prompt or pass less data through template expressions." in message
        assert "Runtime settings validation failed" not in message

    @pytest.mark.asyncio
    async def test_accepts_prompt_within_max_length(self) -> None:
        config: dict[str, object] = {"prompt": "short prompt"}
        await _inject_runtime_settings(config)


class TestExecuteAgenticActivitySettingsIntegration:
    """Tests that execute_agentic_activity handles settings errors correctly."""

    @pytest.mark.asyncio
    async def test_prompt_too_long_raises(self) -> None:
        """Activity raises ApplicationError when prompt exceeds max length."""
        prompt_len = 200000
        config: dict[str, object] = {"prompt": "x" * prompt_len, "timeout": 300}
        with pytest.raises(ApplicationError) as exc_info:
            await execute_agentic_activity(config, None, project_id=str(uuid4()))
        assert exc_info.value.type == "ConfigError"
        message = exc_info.value.message
        assert f"The AI Agent prompt is {prompt_len} characters" in message
        assert "exceeds the limit of" in message
        assert "Shorten the prompt or pass less data through template expressions." in message
        assert message != "Runtime settings validation failed"
        assert "Runtime settings validation failed" not in message

    @pytest.mark.asyncio
    async def test_missing_project_id_raises(self) -> None:
        """Activity raises ApplicationError when project_id is empty."""
        config: dict[str, object] = {"prompt": "test", "timeout": 300}
        with pytest.raises(ApplicationError) as exc_info:
            await execute_agentic_activity(config, None, project_id="")
        assert exc_info.value.type == "ConfigError"
        assert exc_info.value.message == (
            "The AI Agent node could not determine the project context. "
            "This is usually a system error. Try re-saving the workflow or contact your administrator."
        )
        assert "project_id" not in exc_info.value.message
        assert "requires non-empty" not in exc_info.value.message


class TestBuildAgentMetadata:
    """Tests for _build_agent_metadata helper."""

    def test_timeout_not_in_metadata_dict(self) -> None:
        """Verify timeout is NOT in the metadata dict.

        Timeout flows via invoke_agent_async parameter, not metadata.
        """
        config = AgenticExecutorParameters(prompt="test prompt")
        input_config: dict[str, object] = {"prompt": "test prompt", "timeout": 60}
        metadata = _build_agent_metadata(
            config,
            input_config,
            workflow_id="wf-1",
            activity_id="act-1",
            execution_id="exec-1",
            callback_url="https://example.com/callback",
            request_id=None,
        )
        assert "timeout" not in metadata
        assert "timeout_seconds" not in metadata

    def test_includes_core_fields(self) -> None:
        """Verify workflow_id, activity_id, etc are in metadata."""
        config = AgenticExecutorParameters(prompt="test prompt")
        input_config: dict[str, object] = {"prompt": "test prompt"}
        metadata = _build_agent_metadata(
            config,
            input_config,
            workflow_id="wf-123",
            activity_id="act-456",
            execution_id="exec-789",
            callback_url="https://example.com/cb",
            request_id="req-abc",
        )
        assert metadata["workflow_id"] == "wf-123"
        assert metadata["activity_id"] == "act-456"
        assert metadata["execution_id"] == "exec-789"
        assert metadata["activity_name"] == "agentic_v2"
        assert metadata["callback_url"] == "https://example.com/cb"
        assert metadata["request_id"] == "req-abc"
