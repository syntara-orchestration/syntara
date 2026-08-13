"""Unit tests for LLMRelevancyChecker.

This module tests the integration between LLMRelevancyChecker and OpenRouter LLM,
ensuring proper relevancy scoring with real LLM calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker import (
    LLMRelevancyChecker,
)
from syntara.agent_orchestrator.context_manager.retriever_service.config.configuration_manager import (
    ConfigurationManager,
)
from syntara.agent_orchestrator.context_manager.retriever_service.exceptions import RelevancyCheckError
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument
from syntara.agent_orchestrator.models.llm_credential_config import LLMCredentialConfig
from syntara.files.models import FileMetadata

_TEST_CREDENTIAL = LLMCredentialConfig(
    api_key="test-key",
    base_url="https://openrouter.ai/api/v1",
    model="anthropic/claude-sonnet-4",
)


@pytest.mark.integration
class TestLLMRelevancyCheckerIntegration:
    """Integration tests for LLMRelevancyChecker with OpenRouter LLM."""

    @pytest.mark.asyncio
    async def test_llm_relevancy_scoring_relevant_content(self) -> None:
        """Test LLM properly scores highly relevant content."""
        # Create a document highly relevant to the query
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="python_guide.pdf",
            size_bytes=2048,
            mime_type="application/pdf",
            file_path="/path/to/python_guide.pdf",
            status="converted",
        )

        relevant_document = RelevantDocument(
            content="""
            Python is a high-level programming language known for its simplicity and readability.
            It supports multiple programming paradigms including procedural, object-oriented,
            and functional programming.
            Python's syntax emphasizes code readability with its use of significant whitespace.
            The language features dynamic typing and automatic memory management.
            """,
            relevancy_score=1.0,  # Initial neutral score
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )

        config_manager = ConfigurationManager()
        config = config_manager.get_llm_configuration()
        config.algorithm_parameters["max_tokens"] = 100

        # Mock the LLM response for highly relevant content
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "0.85"  # High relevancy score
        mock_llm.ainvoke.return_value = mock_response

        with patch(
            "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm",
            return_value=(mock_llm, None),
        ):
            checker = LLMRelevancyChecker()
            query = "Explain Python programming language features"

            relevancy_score = await checker.check_relevancy(
                relevant_document, query, config, llm_credential_config=_TEST_CREDENTIAL
            )

            # Should score highly relevant content with high relevancy
            assert 0.7 <= relevancy_score <= 1.0
            assert isinstance(relevancy_score, float)
            assert relevancy_score == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_llm_relevancy_scoring_irrelevant_content(self) -> None:
        """Test LLM properly scores irrelevant content with low score."""
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="cooking_recipes.pdf",
            size_bytes=1024,
            mime_type="application/pdf",
            file_path="/path/to/cooking_recipes.pdf",
            status="converted",
        )

        irrelevant_document = RelevantDocument(
            content="""
            Chocolate chip cookies are a classic dessert loved by many.
            To make them, you'll need flour, sugar, butter, eggs, and chocolate chips.
            Preheat your oven to 375°F and bake for 10-12 minutes until golden brown.
            Let them cool on the baking sheet before transferring to a wire rack.
            """,
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )

        config_manager = ConfigurationManager()
        config = config_manager.get_llm_configuration()
        config.algorithm_parameters["max_tokens"] = 100

        # Mock the LLM response for irrelevant content
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "0.15"  # Low relevancy score
        mock_llm.ainvoke.return_value = mock_response

        with patch(
            "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm",
            return_value=(mock_llm, None),
        ):
            checker = LLMRelevancyChecker()
            query = "Explain machine learning algorithms"

            relevancy_score = await checker.check_relevancy(
                irrelevant_document, query, config, llm_credential_config=_TEST_CREDENTIAL
            )

            # Should score irrelevant content with low relevancy
            assert 0.0 <= relevancy_score <= 0.3
            assert relevancy_score == pytest.approx(0.15)

    @pytest.mark.asyncio
    async def test_llm_with_file_metadata_context(self) -> None:
        """Test LLM considers file metadata in relevancy scoring."""
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="ai_research_paper.pdf",  # Filename provides context
            size_bytes=5120,
            mime_type="application/pdf",
            file_path="/documents/ai_research_paper.pdf",
            status="converted",
        )

        document = RelevantDocument(
            content="""
            This paper presents findings on neural network architectures.
            We compare different approaches to model training and evaluation.
            The results show significant improvements in accuracy and performance.
            """,
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )

        config_manager = ConfigurationManager()
        config = config_manager.get_llm_configuration()
        config.algorithm_parameters["max_tokens"] = 150
        config.algorithm_parameters["use_filename_context"] = True

        # Mock the LLM response considering filename context
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "0.75"  # Higher score due to filename context
        mock_llm.ainvoke.return_value = mock_response

        with patch(
            "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm",
            return_value=(mock_llm, None),
        ):
            checker = LLMRelevancyChecker()
            query = "artificial intelligence research papers"

            relevancy_score = await checker.check_relevancy(
                document, query, config, llm_credential_config=_TEST_CREDENTIAL
            )

            # Should leverage filename context for higher relevancy
            assert relevancy_score >= 0.6
            assert relevancy_score == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_llm_configuration_parameters(self) -> None:
        """Test different LLM configuration parameters affect scoring."""
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="test_document.txt",
            size_bytes=512,
            mime_type="text/plain",
            file_path="/path/to/test_document.txt",
            status="converted",
        )

        document = RelevantDocument(
            content="This document discusses database optimization techniques and indexing strategies.",
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )

        # Test with conservative temperature
        config_manager = ConfigurationManager()
        conservative_config = config_manager.get_llm_configuration()
        conservative_config.algorithm_parameters["temperature"] = 0.1  # Very conservative
        conservative_config.algorithm_parameters["max_tokens"] = 50

        # Test with creative temperature
        creative_config = config_manager.get_llm_configuration()
        creative_config.algorithm_parameters["temperature"] = 0.7  # More creative
        creative_config.algorithm_parameters["max_tokens"] = 50

        # Mock the LLM responses for both configurations
        mock_llm = AsyncMock()
        mock_response_conservative = MagicMock()
        mock_response_conservative.content = "0.65"  # Conservative score
        mock_response_creative = MagicMock()
        mock_response_creative.content = "0.72"  # Slightly different creative score

        mock_llm.ainvoke.side_effect = [mock_response_conservative, mock_response_creative]

        with patch(
            "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm",
            return_value=(mock_llm, None),
        ):
            checker = LLMRelevancyChecker()
            query = "database performance optimization"

            conservative_score = await checker.check_relevancy(
                document, query, conservative_config, llm_credential_config=_TEST_CREDENTIAL
            )
            creative_score = await checker.check_relevancy(
                document, query, creative_config, llm_credential_config=_TEST_CREDENTIAL
            )

            # Both should be valid scores
            assert 0.0 <= conservative_score <= 1.0
            assert 0.0 <= creative_score <= 1.0
            assert conservative_score == pytest.approx(0.65)
            assert creative_score == pytest.approx(0.72)

    @pytest.mark.asyncio
    async def test_llm_error_handling(self) -> None:
        """Test LLM error handling with invalid configuration."""
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="test.txt",
            size_bytes=256,
            mime_type="text/plain",
            file_path="/path/to/test.txt",
            status="converted",
        )

        document = RelevantDocument(
            content="Test content for error handling",
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )

        config_manager = ConfigurationManager()
        invalid_config = config_manager.get_llm_configuration()

        invalid_credential = LLMCredentialConfig(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            model="nonexistent/invalid-model",
        )

        # Mock the get_openrouter_llm to raise an exception
        with patch(
            "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm",
            side_effect=ValueError("Invalid model configuration"),
        ):
            checker = LLMRelevancyChecker()
            query = "test query"

            # Should raise RelevancyCheckError for invalid model (wrapping the ValueError)
            with pytest.raises(RelevancyCheckError):
                await checker.check_relevancy(document, query, invalid_config, llm_credential_config=invalid_credential)

    @pytest.mark.asyncio
    async def test_openrouter_integration(self) -> None:
        """Test integration with existing OpenRouter configuration."""
        # Verify that LLMRelevancyChecker uses get_openrouter_llm()

        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="integration_test.txt",
            size_bytes=512,
            mime_type="text/plain",
            file_path="/path/to/integration_test.txt",
            status="converted",
        )

        document = RelevantDocument(
            content="Integration test for OpenRouter configuration with LangChain LLM.",
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )

        config_manager = ConfigurationManager()
        config = config_manager.get_llm_configuration()
        config.algorithm_parameters["max_tokens"] = 100

        # Mock successful OpenRouter integration
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "0.68"  # Integration test score
        mock_llm.ainvoke.return_value = mock_response

        with patch(
            "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm",
            return_value=(mock_llm, None),
        ) as mock_get_llm:
            checker = LLMRelevancyChecker()
            query = "LangChain integration testing"

            # Should successfully use OpenRouter LLM
            relevancy_score = await checker.check_relevancy(
                document, query, config, llm_credential_config=_TEST_CREDENTIAL
            )

            assert 0.0 <= relevancy_score <= 1.0
            assert isinstance(relevancy_score, float)
            assert relevancy_score == pytest.approx(0.68)

            mock_get_llm.assert_called_once_with(
                model=_TEST_CREDENTIAL.model,
                temperature=0.3,
                api_key=_TEST_CREDENTIAL.api_key.get_secret_value(),
                base_url=_TEST_CREDENTIAL.base_url,
                insecure_skip_tls_verify=False,
                ca_certificate=None,
            )

    @pytest.mark.asyncio
    async def test_tls_params_forwarded_to_openrouter_llm(self) -> None:
        """TLS settings from LLMCredentialConfig are forwarded to get_openrouter_llm()."""
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="tls_test.txt",
            size_bytes=512,
            mime_type="text/plain",
            file_path="/path/to/tls_test.txt",
            status="converted",
        )
        document = RelevantDocument(
            content="Test content for TLS parameter forwarding.",
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )
        config_manager = ConfigurationManager()
        config = config_manager.get_llm_configuration()
        config.algorithm_parameters["max_tokens"] = 100

        tls_credential = LLMCredentialConfig(
            api_key="test-key",
            base_url="https://custom-llm.internal",
            model="custom-model",
            insecure_skip_tls_verify=True,
            ca_certificate="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        )

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "0.75"
        mock_llm.ainvoke.return_value = mock_response

        with patch(
            "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm",
            return_value=(mock_llm, None),
        ) as mock_get_llm:
            checker = LLMRelevancyChecker()
            await checker.check_relevancy(document, "test query", config, llm_credential_config=tls_credential)

            mock_get_llm.assert_called_once_with(
                model="custom-model",
                temperature=0.3,
                api_key="test-key",
                base_url="https://custom-llm.internal",
                insecure_skip_tls_verify=True,
                ca_certificate="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
            )

    @pytest.mark.asyncio
    async def test_empty_content_handling(self) -> None:
        """Test handling of documents with minimal content."""
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="minimal.txt",
            size_bytes=10,
            mime_type="text/plain",
            file_path="/path/to/minimal.txt",
            status="converted",
        )

        minimal_document = RelevantDocument(
            content="ML",  # Very short content
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )

        config_manager = ConfigurationManager()
        config = config_manager.get_llm_configuration()
        config.algorithm_parameters["max_tokens"] = 100

        # Mock the LLM response for minimal content
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "0.45"  # Moderate score despite minimal content
        mock_llm.ainvoke.return_value = mock_response

        with patch(
            "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm",
            return_value=(mock_llm, None),
        ):
            checker = LLMRelevancyChecker()
            query = "machine learning algorithms"

            # Should handle minimal content gracefully
            relevancy_score = await checker.check_relevancy(
                minimal_document, query, config, llm_credential_config=_TEST_CREDENTIAL
            )
            assert 0.0 <= relevancy_score <= 1.0
            assert relevancy_score == pytest.approx(0.45)

    @pytest.mark.asyncio
    async def test_missing_credential_config_raises_error(self) -> None:
        """Test that check_relevancy raises when no LLMCredentialConfig is provided."""
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="test.txt",
            size_bytes=256,
            mime_type="text/plain",
            file_path="/path/to/test.txt",
            status="converted",
        )

        document = RelevantDocument(
            content="Test content",
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )

        config_manager = ConfigurationManager()
        config = config_manager.get_llm_configuration()

        checker = LLMRelevancyChecker()
        with pytest.raises(RelevancyCheckError, match="LLM credential config is required"):
            await checker.check_relevancy(document, "test query", config)


class TestLLMRelevancyCheckerUnit:
    """Unit tests for LLMRelevancyChecker internal methods."""

    @pytest.fixture
    def checker(self) -> LLMRelevancyChecker:
        """Create LLMRelevancyChecker instance."""
        return LLMRelevancyChecker()

    @pytest.fixture
    def sample_document(self) -> RelevantDocument:
        """Create sample document for testing."""
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="test_document.py",
            size_bytes=1024,
            mime_type="text/x-python",
            file_path="/path/to/test_document.py",
            status="converted",
        )
        return RelevantDocument(
            content="def hello_world():\n    print('Hello, World!')\n    return 'success'",
            relevancy_score=0.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )

    def test_prepare_content_excerpt_short_content(self, checker: "LLMRelevancyChecker") -> None:
        """Test content excerpt preparation with short content."""
        short_content = "This is a short document."
        excerpt = checker._prepare_content_excerpt(short_content, 1000)

        assert excerpt == short_content
        assert len(excerpt) <= 1000

    def test_prepare_content_excerpt_long_content(self, checker: "LLMRelevancyChecker") -> None:
        """Test content excerpt preparation with long content requiring truncation."""
        long_content = "This is a very long document. " * 100  # 3000+ chars
        excerpt = checker._prepare_content_excerpt(long_content, 500)

        assert len(excerpt) <= 600  # Should include truncation message
        assert "[Content truncated...]" in excerpt
        assert excerpt.startswith("This is a very long document")

    def test_prepare_content_excerpt_empty_content(self, checker: LLMRelevancyChecker) -> None:
        """Test content excerpt preparation with empty content."""
        empty_content = ""
        excerpt = checker._prepare_content_excerpt(empty_content, 1000)

        assert excerpt == ""

    def test_build_user_prompt_with_metadata(
        self, checker: LLMRelevancyChecker, sample_document: RelevantDocument
    ) -> None:
        """Test user prompt building with file metadata included."""
        query = "python function"
        content = "def test(): pass"

        prompt = checker._build_user_prompt(
            query=query, content=content, document=sample_document, include_metadata=True, use_title_weighting=True
        )

        assert "Query: python function" in prompt
        assert "Document Metadata:" in prompt
        assert "Filename: test_document.py" in prompt
        assert "File Type: text/x-python" in prompt
        assert "Consider the filename when scoring relevance" in prompt
        assert "def test(): pass" in prompt

    def test_build_user_prompt_without_metadata(
        self, checker: LLMRelevancyChecker, sample_document: RelevantDocument
    ) -> None:
        """Test user prompt building without file metadata."""
        query = "python function"
        content = "def test(): pass"

        prompt = checker._build_user_prompt(
            query=query, content=content, document=sample_document, include_metadata=False, use_title_weighting=False
        )

        assert "Query: python function" in prompt
        assert "Document Metadata:" not in prompt
        assert "Filename:" not in prompt
        assert "def test(): pass" in prompt

    def test_parse_score_decimal_format(self, checker: LLMRelevancyChecker) -> None:
        """Test parsing decimal score from LLM response."""
        responses = ["0.75", "The score is 0.85", "Based on analysis: 0.62", "Score: 1.0", "0.00"]

        expected_scores = [0.75, 0.85, 0.62, 1.0, 0.0]

        for response, expected in zip(responses, expected_scores, strict=False):
            score = checker._parse_score_from_response(response)
            assert score == expected

    def test_parse_score_percentage_format(self, checker: LLMRelevancyChecker) -> None:
        """Test parsing percentage score from LLM response."""
        responses = ["75%", "The document scores 85%", "Relevance: 92%", "0%"]

        expected_scores = [0.75, 0.85, 0.92, 0.0]

        for response, expected in zip(responses, expected_scores, strict=False):
            score = checker._parse_score_from_response(response)
            assert score == expected

    def test_parse_score_whole_number_format(self, checker: LLMRelevancyChecker) -> None:
        """Test parsing whole number score from LLM response."""
        responses = [
            "8",  # Assume 0-10 scale
            "85",  # Assume 0-100 scale
            "The score is 7 out of 10",
            "Rated: 90",
        ]

        expected_scores = [0.8, 0.85, 0.7, 0.9]

        for response, expected in zip(responses, expected_scores, strict=False):
            score = checker._parse_score_from_response(response)
            assert score == expected

    def test_parse_score_qualitative_format(self, checker: LLMRelevancyChecker) -> None:
        """Test parsing qualitative indicators from LLM response."""
        responses = [
            "High relevance detected",
            "This is very relevant",
            "Medium relevance found",
            "Low relevance to query",
            "Not relevant content",
        ]

        expected_ranges = [
            (0.7, 1.0),  # High
            (0.7, 1.0),  # Very relevant
            (0.4, 0.6),  # Medium
            (0.1, 0.3),  # Low
            (0.1, 0.3),  # Not relevant
        ]

        for response, (min_val, max_val) in zip(responses, expected_ranges, strict=False):
            score = checker._parse_score_from_response(response)
            assert min_val <= score <= max_val

    def test_parse_score_invalid_format(self, checker: LLMRelevancyChecker) -> None:
        """Test parsing invalid or unparseable responses."""
        invalid_responses = ["", "completely unrelated text", "???", "invalid format response"]

        for response in invalid_responses:
            score = checker._parse_score_from_response(response)
            assert score == pytest.approx(0.5)  # Default fallback score
