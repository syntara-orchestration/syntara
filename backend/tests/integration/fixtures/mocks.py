"""Mock fixtures specific to integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
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
