"""Mock fixtures specific to integration tests."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def mock_openrouter_llm() -> Generator[MagicMock, None, None]:
    """Mock get_openrouter_llm to avoid requiring OPENROUTER_API_KEY."""
    from langchain_core.messages import AIMessage

    mock_llm = MagicMock()
    mock_llm_with_tools = AsyncMock()
    mock_llm_with_tools.ainvoke = AsyncMock(
        return_value=AIMessage(
            content="Mock LLM response for testing",
            response_metadata={"model": "mock-model", "finish_reason": "stop"},
        )
    )
    mock_llm.bind_tools = MagicMock(return_value=mock_llm_with_tools)
    mock_llm.model_name = "mock-model"

    mock_compressor = AsyncMock()
    mock_compressor.compress = AsyncMock(return_value="Compressed content for testing")

    with (
        patch(
            "syntara.agent_orchestrator.executor.invocation_executor.get_openrouter_llm",
            return_value=(mock_llm, None),
        ),
        patch(
            "syntara.agent_orchestrator.context_manager.compressor.CompressorService",
            return_value=mock_compressor,
        ),
        patch(
            "syntara.agent_orchestrator.services.orchestration_service.OrchestrationService._get_tools",
            return_value=[],
        ),
    ):
        yield mock_llm


@pytest.fixture
def local_script_execution() -> Generator[None, None, None]:
    """Substitute container execution for workflow tests without a live cluster.

    Keep real script output, failures and timeouts while exercising the surrounding
    Temporal workflow. The OpenShift HTTP lifecycle is tested separately.
    """
    from syntara.workflows.workflow_engine.activities.script_activity import _execute_script_common

    async def execute(
        language: str,
        code: str,
        environment: dict[str, str] | None,
        timeout_seconds: float,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        command = ["bash", "-c", code] if language == "bash" else [sys.executable, "-c", code]
        return await _execute_script_common(command, environment, timeout_seconds, max_output_bytes)

    with patch("syntara.workflows.workflow_engine.activities.script_activity.execute_openshift_script", execute):
        yield
