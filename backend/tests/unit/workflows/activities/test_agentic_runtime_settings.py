"""Tests for agentic activity runtime settings injection."""

from collections.abc import Generator
from unittest.mock import patch
from uuid import uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.agentic_activity import (
    _inject_runtime_settings,
    execute_agentic_activity,
)


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
