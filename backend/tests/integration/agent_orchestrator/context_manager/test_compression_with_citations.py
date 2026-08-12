"""Integration tests for LLM compression with structured citations.

Tests the RH1 compression logic when documents exceed token budget
and require LLM summarization with proper citation format.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import AsyncMock, Mock

import pytest

from syntara.agent_orchestrator.context_manager.compressor import CompressorService
from tests.fixtures.settings import FakeSettingsCache


class TestCompressionWithCitations:
    """Tests for LLM compression with structured citations."""

    @pytest.fixture(autouse=True)
    def _mock_runtime_settings(  # type: ignore[misc]
        self, override_runtime_settings: Callable[..., AbstractContextManager[FakeSettingsCache]]
    ) -> None:
        """Auto-mock get_runtime_settings for compressor tests."""
        with override_runtime_settings():
            yield

    async def test_documents_exceeding_budget_trigger_compression(self, mock_token_calculator: Mock) -> None:
        """Test that documents exceeding token budget trigger LLM compression."""
        # Arrange
        # Token counting call sequence:
        # 1. First call: count tokens in concatenated input documents (1000 - exceeds budget)
        # 2. Second call: count tokens in LLM-compressed output (150 - within budget)
        mock_token_calculator.count_tokens.side_effect = [1000, 150]

        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = (
            "According to Document 1, the key information includes important details. "
            "Document 2 provides supporting evidence with critical facts."
        )
        mock_llm.ainvoke.return_value = mock_response

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = [
            "Very long document with lots of content that exceeds token limits",
            "Another lengthy document with extensive information",
        ]

        max_tokens = 200  # Smaller than the first token count

        # Act
        result = await compressor.compress(
            data=documents,
            max_tokens=max_tokens,
            strategy="greedy",
            goal="Extract key information",
        )

        # Assert
        assert result == mock_response.content
        assert "According to Document 1" in result
        assert "Document 2" in result

        # Verify LLM was called
        mock_llm.ainvoke.assert_called_once()
        call_args = mock_llm.ainvoke.call_args[0][0]
        prompt_content = call_args[0]["content"]

        # Check that prompt contains proper structure
        assert "Summarize the following documents" in prompt_content
        assert "Extract key information" in prompt_content
        assert str(max_tokens) in prompt_content
        assert "Document 1:" in prompt_content
        assert "Document 2:" in prompt_content

    async def test_compression_with_goal_context(self, mock_token_calculator: Mock) -> None:
        """Test that goal context is properly incorporated into LLM prompt."""
        # Arrange
        # Token counting: input content (500) exceeds budget, compressed output (100) fits
        mock_token_calculator.count_tokens.side_effect = [500, 100]

        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = "According to Document 1, pricing information shows $100."
        mock_llm.ainvoke.return_value = mock_response

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = ["Product details and pricing information"]

        # Act
        result = await compressor.compress(
            data=documents,
            max_tokens=150,
            strategy="greedy",
            goal="Extract pricing information",
        )

        # Assert
        assert "pricing" in result.lower()

        # Verify goal appears in prompt
        call_args = mock_llm.ainvoke.call_args[0][0]
        prompt_content = call_args[0]["content"]
        assert "Extract pricing information" in prompt_content

    async def test_compression_fails_fast_on_llm_failure(self, mock_token_calculator: Mock) -> None:
        """Test that compression fails fast when LLM compression fails."""
        # Arrange
        mock_token_calculator.count_tokens.return_value = 500

        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = Exception("LLM service unavailable")

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = ["A" * 2000]  # Very long content

        # Act & Assert - exceptions bubble up to caller
        with pytest.raises(Exception, match="LLM service unavailable"):
            await compressor.compress(data=documents, max_tokens=100, strategy="greedy")

    async def test_document_formatting_for_llm_prompt(self, mock_token_calculator: Mock) -> None:
        """Test that documents are properly formatted with numeric labels for LLM."""
        # Arrange
        # Token counting: input (300) exceeds budget, output (80) fits
        mock_token_calculator.count_tokens.side_effect = [300, 80]

        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = "According to Document 1, first info. Document 3 mentions third detail."
        mock_llm.ainvoke.return_value = mock_response

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = ["First document content", "Second document content", "Third document content"]

        # Act
        await compressor.compress(data=documents, max_tokens=100, strategy="greedy")

        # Assert
        call_args = mock_llm.ainvoke.call_args[0][0]
        prompt_content = call_args[0]["content"]

        # Check numeric labeling
        assert "Document 1:" in prompt_content
        assert "Document 2:" in prompt_content
        assert "Document 3:" in prompt_content

    async def test_compression_token_verification(self, mock_token_calculator: Mock) -> None:
        """Test that compressed content token count is verified through LLM compression."""
        # Arrange
        # Token counting: original content (500) triggers compression, result (75) verified
        mock_token_calculator.count_tokens.side_effect = [500, 75]

        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = "Compressed summary with citations."
        mock_llm.ainvoke.return_value = mock_response

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = ["Long content"]

        # Act
        result = await compressor.compress(data=documents, max_tokens=100, strategy="greedy")

        # Assert
        assert result == mock_response.content

        # Verify LLM compression was triggered and token verification occurred
        assert mock_llm.ainvoke.called, "LLM should be called for compression"
        assert mock_token_calculator.count_tokens.call_count == 2, (
            "Token calculator should verify both input and output"
        )

        # Verify the LLM was called with a proper prompt
        call_args = mock_llm.ainvoke.call_args
        assert call_args is not None
        prompt_content = call_args[0][0][0]["content"]
        assert "Summarize the following documents" in prompt_content
        assert "100 tokens" in prompt_content  # max_tokens mentioned in prompt

    async def test_default_goal_when_none_provided(self, mock_token_calculator: Mock) -> None:
        """Test that default goal is used when none is provided."""
        # Arrange
        # Token counting: input (200) exceeds budget, compressed output (50) fits
        mock_token_calculator.count_tokens.side_effect = [200, 50]

        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = "Summary with default goal."
        mock_llm.ainvoke.return_value = mock_response

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = ["Content"]

        # Act
        await compressor.compress(
            data=documents,
            max_tokens=100,
            strategy="greedy",
            goal=None,  # No goal provided
        )

        # Assert
        call_args = mock_llm.ainvoke.call_args[0][0]
        prompt_content = call_args[0]["content"]
        assert "summarize the key information" in prompt_content

    async def test_single_document_compression(self, mock_token_calculator: Mock) -> None:
        """Test compression with single document input (string)."""
        # Arrange
        # Token counting: input (300) exceeds budget, compressed result (50) fits
        mock_token_calculator.count_tokens.side_effect = [300, 50]

        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = "Compressed single document summary."
        mock_llm.ainvoke.return_value = mock_response

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        # Single string document
        document = "Very long single document that exceeds the token budget and needs compression"

        # Act
        result = await compressor.compress(data=document, max_tokens=100, strategy="greedy")

        # Assert
        assert result == mock_response.content

        # Verify LLM prompt formatting for single document
        call_args = mock_llm.ainvoke.call_args[0][0]
        prompt_content = call_args[0]["content"]
        # Single document should not have "Document 1:" prefix in the original content
        assert document in prompt_content

    async def test_very_large_single_document_compression(self, mock_token_calculator: Mock) -> None:
        """Test compression of a single document that individually exceeds budget."""
        # Arrange
        # Token counting: single large document (2000) far exceeds budget, compressed (80) fits
        mock_token_calculator.count_tokens.side_effect = [2000, 80]

        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = "Highly compressed summary of the large document."
        mock_llm.ainvoke.return_value = mock_response

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        # Very large single document
        large_document = "Very " * 1000 + "large document that individually exceeds token limits"

        # Act
        result = await compressor.compress(
            data=large_document,  # Single string, not list
            max_tokens=100,
            strategy="greedy",
            goal="Extract key points",
        )

        # Assert
        assert result == mock_response.content

        # Verify LLM was called for compression
        mock_llm.ainvoke.assert_called_once()
        call_args = mock_llm.ainvoke.call_args[0][0]
        prompt_content = call_args[0]["content"]

        # Should contain the large document and goal
        assert "Extract key points" in prompt_content
        assert large_document in prompt_content

    async def test_token_calculator_failure_handling(self, mock_token_calculator: Mock) -> None:
        """Test that TokenCalculator failures are properly handled."""
        # Arrange
        # First call (input validation) fails
        mock_token_calculator.count_tokens.side_effect = Exception("Token calculation failed")

        mock_llm = AsyncMock()
        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        # Act & Assert
        with pytest.raises(Exception, match="Token calculation failed"):
            await compressor.compress(data=["Test content"], max_tokens=100, strategy="greedy")

        # Verify token calculator was called before failure
        mock_token_calculator.count_tokens.assert_called_once()

    async def test_token_calculator_failure_during_verification(self, mock_token_calculator: Mock) -> None:
        """Test TokenCalculator failure during output verification."""
        # Arrange
        # First call succeeds (triggers compression), second call fails (verification)
        mock_token_calculator.count_tokens.side_effect = [500, Exception("Verification failed")]

        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = "Compressed content"
        mock_llm.ainvoke.return_value = mock_response

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        # Act & Assert
        with pytest.raises(Exception, match="Verification failed"):
            await compressor.compress(
                data=["Long content that exceeds budget"],
                max_tokens=100,
                strategy="greedy",
            )

        # Verify both services were called before failure
        assert mock_token_calculator.count_tokens.call_count == 2
        mock_llm.ainvoke.assert_called_once()

    async def test_llm_response_without_proper_citations(self, mock_token_calculator: Mock) -> None:
        """Test handling of LLM responses that don't include proper document citations."""
        # Arrange
        # Token counting: input exceeds budget, compressed output fits
        mock_token_calculator.count_tokens.side_effect = [400, 60]

        mock_llm = AsyncMock()
        mock_response = Mock()
        # LLM response without proper citation format - missing "Document X" references
        mock_response.content = "The key information shows important details and critical facts."
        mock_llm.ainvoke.return_value = mock_response

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = ["First document with details", "Second document with facts"]

        # Act
        result = await compressor.compress(data=documents, max_tokens=100, strategy="greedy")

        # Assert
        # Service should still return the result even if citations are malformed
        # This tests the robustness - we don't fail if LLM doesn't follow citation format perfectly
        assert result == mock_response.content
        assert "key information" in result

        # Verify LLM was called with proper citation instructions
        call_args = mock_llm.ainvoke.call_args[0][0]
        prompt_content = call_args[0]["content"]
        assert "Use structured citations" in prompt_content

    async def test_llm_response_with_mixed_citation_quality(self, mock_token_calculator: Mock) -> None:
        """Test LLM response with some good citations and some missing."""
        # Arrange
        # Token counting: input exceeds budget, compressed output fits
        mock_token_calculator.count_tokens.side_effect = [500, 85]

        mock_llm = AsyncMock()
        mock_response = Mock()
        # Mixed quality response: some citations present, some missing
        mock_response.content = (
            "According to Document 1, pricing is $100. There are additional features mentioned but sources unclear."
        )
        mock_llm.ainvoke.return_value = mock_response

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = ["Pricing document with $100", "Features document", "Support document"]

        # Act
        result = await compressor.compress(
            data=documents,
            max_tokens=120,
            strategy="greedy",
            goal="Extract pricing and features",
        )

        # Assert
        # Should accept the response even with imperfect citations
        assert result == mock_response.content
        assert "Document 1" in result
        assert "pricing" in result.lower()

        # Verify proper prompt structure was provided
        call_args = mock_llm.ainvoke.call_args[0][0]
        prompt_content = call_args[0]["content"]
        assert "Document 1:" in prompt_content
        assert "Document 2:" in prompt_content
        assert "Document 3:" in prompt_content

    async def test_goal_parameter_with_very_long_text(self, mock_token_calculator: Mock) -> None:
        """Test goal parameter with very long text that might affect prompt construction."""
        # Arrange
        # Token counting: input exceeds budget, compressed output fits
        mock_token_calculator.count_tokens.side_effect = [300, 75]

        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = "Focused summary based on the detailed goal."
        mock_llm.ainvoke.return_value = mock_response

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = ["Document content"]

        # Very long goal text
        long_goal = (
            "Extract very specific information about "
            + "detailed requirements " * 100
            + "and ensure comprehensive analysis"
        )

        # Act
        result = await compressor.compress(data=documents, max_tokens=100, strategy="greedy", goal=long_goal)

        # Assert
        assert result == mock_response.content

        # Verify the long goal is included in the prompt
        call_args = mock_llm.ainvoke.call_args[0][0]
        prompt_content = call_args[0]["content"]
        assert long_goal in prompt_content

    async def test_goal_parameter_with_special_characters(self, mock_token_calculator: Mock) -> None:
        """Test goal parameter with special characters and formatting."""
        # Arrange
        # Token counting: input exceeds budget, compressed output fits
        mock_token_calculator.count_tokens.side_effect = [250, 80]

        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = "Summary handling special characters correctly."
        mock_llm.ainvoke.return_value = mock_response

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = ["Technical documentation"]

        # Goal with special characters, newlines, and formatting
        special_goal = """Extract:
        1. Key metrics (>95% accuracy)
        2. Performance data [$100-$500 range]
        3. Technical specs & requirements
        Note: Focus on "critical" components only!"""

        # Act
        result = await compressor.compress(
            data=documents,
            max_tokens=120,
            strategy="greedy",
            goal=special_goal,
        )

        # Assert
        assert result == mock_response.content

        # Verify special characters are properly handled in prompt
        call_args = mock_llm.ainvoke.call_args[0][0]
        prompt_content = call_args[0]["content"]
        assert special_goal in prompt_content
        assert "Key metrics" in prompt_content
        assert "$100-$500" in prompt_content
        assert '"critical"' in prompt_content

    async def test_goal_parameter_empty_string(self, mock_token_calculator: Mock) -> None:
        """Test goal parameter with empty string (should use default)."""
        # Arrange
        # Token counting: input exceeds budget, compressed output fits
        mock_token_calculator.count_tokens.side_effect = [200, 50]

        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = "Default goal summary."
        mock_llm.ainvoke.return_value = mock_response

        compressor = CompressorService(token_calculator=mock_token_calculator, llm=mock_llm)

        documents = ["Content to compress"]

        # Act
        result = await compressor.compress(
            data=documents,
            max_tokens=80,
            strategy="greedy",
            goal="",  # Empty string goal
        )

        # Assert
        assert result == mock_response.content

        # Verify default goal text is used
        call_args = mock_llm.ainvoke.call_args[0][0]
        prompt_content = call_args[0]["content"]
        assert "summarize the key information" in prompt_content
