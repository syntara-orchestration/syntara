"""Integration tests for context compression pass-through behavior.

Tests the RH1 binary decision logic where documents within token budget
pass through unchanged without compression.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import AsyncMock, Mock

import pytest

from syntara.agent_orchestrator.context_manager.compressor import CompressorService
from tests.fixtures.settings import FakeSettingsCache


class TestCompressionPassthrough:
    """Tests for compression pass-through when documents are within token budget."""

    @pytest.fixture(autouse=True)
    def _mock_runtime_settings(  # type: ignore[misc]
        self, override_runtime_settings: Callable[..., AbstractContextManager[FakeSettingsCache]]
    ) -> None:
        """Auto-mock get_runtime_settings for compressor tests."""
        with override_runtime_settings():
            yield

    async def test_documents_within_budget_pass_through_unchanged(self, mock_token_calculator: Mock) -> None:
        """Test that documents fitting within token budget pass through without compression."""
        # Arrange
        mock_token_calculator.count_tokens.return_value = 100  # Small token count

        mock_llm = AsyncMock()
        mock_llm.model_name = "test-model"
        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = ["Short document content", "Another brief text"]

        max_tokens = 500  # Larger than the mocked token count

        # Act
        result = await compressor.compress(data=documents, max_tokens=max_tokens, strategy="greedy")

        # Assert - should return concatenated original content
        expected_content = "Document 1:\nShort document content\n\nDocument 2:\nAnother brief text"
        assert result == expected_content

        # Verify token calculation was called with model name
        mock_token_calculator.count_tokens.assert_called_once_with(expected_content, model_name="test-model")

    async def test_single_document_within_budget(self, mock_token_calculator: Mock) -> None:
        """Test pass-through behavior with single document within budget."""
        # Arrange
        mock_token_calculator.count_tokens.return_value = 50

        mock_llm = AsyncMock()
        mock_llm.model_name = "test-model"
        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        # Single string input
        document = "Single document content"

        # Act
        result = await compressor.compress(data=document, max_tokens=100, strategy="greedy")

        # Assert
        expected_content = "Single document content"
        assert result == expected_content

    async def test_document_concatenation_format(self, mock_token_calculator: Mock) -> None:
        """Test that documents are concatenated with proper formatting."""
        # Arrange
        mock_token_calculator.count_tokens.return_value = 50

        mock_llm = AsyncMock()
        mock_llm.model_name = "test-model"
        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = ["First doc", "Second doc", "Third doc"]

        # Act
        result = await compressor.compress(data=documents, max_tokens=200, strategy="greedy")

        # Assert - check proper document separation
        expected_lines = ["Document 1:", "First doc", "", "Document 2:", "Second doc", "", "Document 3:", "Third doc"]
        assert result == "\n".join(expected_lines)

    async def test_goal_parameter_in_passthrough(self, mock_token_calculator: Mock) -> None:
        """Test that goal parameter is accepted but not used in passthrough case."""
        # Arrange
        mock_token_calculator.count_tokens.return_value = 50

        mock_llm = AsyncMock()
        mock_llm.model_name = "test-model"
        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = ["Short content"]

        # Act
        result = await compressor.compress(
            data=documents,
            max_tokens=100,
            strategy="greedy",
            goal="Extract pricing information",
        )

        # Assert - should pass through unchanged despite goal
        expected_content = "Short content"
        assert result == expected_content
