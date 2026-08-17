"""Fixtures for document-conversion → invocation pipeline integration tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from syntara.agent_orchestrator.token_manager.models import UserTokenConfig


@pytest.fixture
async def test_user_token_config(test_db_session, test_user) -> UserTokenConfig:
    """Token config so assembly can validate budgets during pipeline tests."""
    config = UserTokenConfig(
        user_id=test_user.id,
        token_limit=1000000,
        window_duration_seconds=3600,
        model_name="gpt-4",
    )
    test_db_session.add(config)
    await test_db_session.commit()
    return config


@pytest.fixture
def mock_relevancy_checker() -> Generator[AsyncMock, None, None]:
    """Mock LLM relevancy so uploaded docs are not filtered out without an API key."""
    with patch(
        "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm"
    ) as mock_get_checker_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AIMessage(content="Relevancy Score: 0.85\n\nHighly relevant document.")
        # get_openrouter_llm returns (llm, optional httpx client)
        mock_get_checker_llm.return_value = (mock_llm, None)
        yield mock_llm
