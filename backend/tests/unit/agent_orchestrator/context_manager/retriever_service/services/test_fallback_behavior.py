"""Integration tests for LLM failure fallback behavior.

This module tests the fallback mechanism from LLM-based relevancy checking
to keyword-based checking when LLM services are unavailable.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.context_manager.retriever_service.checkers.keyword_relevancy_checker import (
    KeywordRelevancyChecker,
)
from syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker import (
    LLMRelevancyChecker,
)
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevancy_configuration import (
    RelevancyConfiguration,
)
from syntara.agent_orchestrator.context_manager.retriever_service.registries.relevancy_registry import RelevancyRegistry
from syntara.agent_orchestrator.context_manager.retriever_service.registries.retriever_registry import RetrieverRegistry
from syntara.agent_orchestrator.context_manager.retriever_service.services.retriever_service import RetrieverService
from syntara.agent_orchestrator.models import Invocation
from syntara.core.constants import CONTEXT_KEY_FILE_IDS
from syntara.files.models import FileMetadata, FileStatus

from .conftest import TestUploadedFileRetriever, async_session_generator


class MockLLMError(Exception):
    """Custom exception for test LLM failures."""


@pytest.fixture
def llm_config() -> RelevancyConfiguration:
    """Create a standard LLM relevancy configuration."""
    return RelevancyConfiguration(
        checker_type="llm",
        similarity_threshold=0.3,  # Lower threshold so fallback documents pass filtering
        max_results=10,
        ranking_weights={},
        algorithm_parameters={"model": "anthropic/claude-3.5-sonnet", "temperature": 0.3},
        grounding_parameters={
            "context_window_size": 4000,
            "include_file_metadata": True,
            "use_title_weighting": False,
        },
        recency_weight=0.1,
        mmr_settings={},
    )


@pytest.fixture
def keyword_config() -> RelevancyConfiguration:
    """Create a standard keyword relevancy configuration."""
    return RelevancyConfiguration(
        checker_type="keyword",
        similarity_threshold=0.1,  # Lower threshold for more lenient matching
        max_results=10,
        ranking_weights={},
        algorithm_parameters={"case_sensitive": False, "phrase_bonus_multiplier": 1.5},
        grounding_parameters={},
        recency_weight=0.1,
        mmr_settings={},
    )


@pytest.fixture
def llm_config_strict() -> RelevancyConfiguration:
    """Create a strict LLM relevancy configuration (no keyword fallback)."""
    return RelevancyConfiguration(
        checker_type="llm",
        similarity_threshold=0.5,
        max_results=10,
        ranking_weights={},
        algorithm_parameters={"model": "anthropic/claude-3.5-sonnet"},
        grounding_parameters={
            "context_window_size": 4000,
            "include_file_metadata": True,
            "use_title_weighting": False,
        },
        recency_weight=0.1,
        mmr_settings={},
    )


@pytest.fixture
def configured_retriever_registry() -> RetrieverRegistry:
    """Create a RetrieverRegistry with TestUploadedFileRetriever registered."""
    registry = RetrieverRegistry()
    registry.register_retriever("uploaded_file", TestUploadedFileRetriever)
    return registry


@pytest.fixture
def configured_relevancy_registry(
    llm_config: RelevancyConfiguration, keyword_config: RelevancyConfiguration
) -> RelevancyRegistry:
    """Create a RelevancyRegistry with both LLM and keyword checkers registered."""
    registry = RelevancyRegistry()
    registry.register_checker("llm", LLMRelevancyChecker, llm_config)
    registry.register_checker("keyword", KeywordRelevancyChecker, keyword_config)
    return registry


@pytest.fixture
def configured_relevancy_registry_llm_only(llm_config_strict: RelevancyConfiguration) -> RelevancyRegistry:
    """Create a RelevancyRegistry with only LLM checker registered (no fallback)."""
    registry = RelevancyRegistry()
    registry.register_checker("llm", LLMRelevancyChecker, llm_config_strict)
    return registry


def create_file_metadata_with_content(temp_path: Path, filename: str, content: str) -> FileMetadata:
    """Helper function to create FileMetadata with associated content file."""
    content_file = temp_path / f"{filename}.txt"
    content_file.write_text(content, encoding="utf-8")

    return FileMetadata(
        id=uuid4(),
        filename=f"{filename}.pdf",
        size_bytes=len(content),
        mime_type="application/pdf",
        file_path=str(temp_path / f"{filename}.pdf"),
        status=FileStatus.CONVERTED,
        converted_content_path=str(content_file),
    )


@pytest.mark.integration
class TestFallbackBehavior:
    """Integration tests for LLM failure fallback to keyword checking."""

    @pytest.mark.asyncio
    async def test_llm_failure_triggers_keyword_fallback(
        self,
        configured_retriever_registry: RetrieverRegistry,
        configured_relevancy_registry: RelevancyRegistry,
        mock_file_manager: MagicMock,
    ) -> None:
        """Test that LLM failure automatically triggers keyword fallback."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test document using helper function
            test_content = "This document discusses Python programming and machine learning algorithms."
            file_metadata = create_file_metadata_with_content(temp_path, "test_document", test_content)

            # Set up mock FileManager for TestUploadedFileRetriever
            file_ids = (file_metadata.id,)
            mock_file_manager._test_file_metadata_store[file_ids] = [file_metadata]
            TestUploadedFileRetriever._test_file_manager = mock_file_manager

            # Setup mock session and invocation
            mock_session = MagicMock(spec=AsyncSession)
            invocation_id = uuid4()
            mock_invocation = Invocation(
                id=invocation_id,
                prompt="test prompt",
                session_id="test_session",
                context_data={CONTEXT_KEY_FILE_IDS: [str(fid) for fid in file_ids]},
            )
            mock_session.get.return_value = mock_invocation

            # Create service with configured registries
            service = RetrieverService(
                session_factory=lambda: async_session_generator(mock_session),
                retriever_registry_factory=lambda: configured_retriever_registry,
                relevancy_registry_factory=lambda: configured_relevancy_registry,
            )

            # Mock LLM failure
            with patch(
                "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm"
            ) as mock_llm:
                mock_llm.side_effect = Exception("LLM service unavailable")

                query = "Python programming"

                results = await service.retrieve_relevant_documents(invocation_id, query)

                # Should return exactly 1 document matched by KeywordRelevancyChecker
                assert len(results) == 1, f"Expected exactly 1 document from keyword fallback, got {len(results)}"

                # The single result should have fallback metadata indicating keyword fallback was used
                doc = results[0]
                assert doc.retrieval_metadata["primary_checker_failed"] is True
                assert doc.retrieval_metadata["relevancy_checker_used"] == "fallback"
                assert doc.retrieval_metadata["relevancy_checker_type"] == "keyword"

                # Document should contain content that matches the query "Python programming"
                assert "Python" in doc.content or "python" in doc.content.lower()
                assert "programming" in doc.content.lower()

                # Document should have a relevancy score from keyword matching
                assert doc.relevancy_score > 0.0, "Keyword fallback should assign non-zero relevancy score"

    @pytest.mark.asyncio
    async def test_llm_timeout_triggers_fallback(
        self,
        configured_retriever_registry: RetrieverRegistry,
        configured_relevancy_registry: RelevancyRegistry,
        mock_file_manager: MagicMock,
    ) -> None:
        """Test that LLM timeout triggers keyword fallback."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test document using helper function
            test_content = "Machine learning and artificial intelligence concepts explained."
            file_metadata = create_file_metadata_with_content(temp_path, "timeout_test", test_content)

            # Set up mock FileManager for TestUploadedFileRetriever
            file_ids = (file_metadata.id,)
            mock_file_manager._test_file_metadata_store[file_ids] = [file_metadata]
            TestUploadedFileRetriever._test_file_manager = mock_file_manager

            # Setup mock session and invocation
            mock_session = MagicMock(spec=AsyncSession)
            invocation_id = uuid4()
            mock_invocation = Invocation(
                id=invocation_id,
                prompt="test prompt",
                session_id="test_session",
                context_data={CONTEXT_KEY_FILE_IDS: [str(fid) for fid in file_ids]},
            )
            mock_session.get.return_value = mock_invocation

            # Create service with configured registries
            service = RetrieverService(
                session_factory=lambda: async_session_generator(mock_session),
                retriever_registry_factory=lambda: configured_retriever_registry,
                relevancy_registry_factory=lambda: configured_relevancy_registry,
            )

            # Mock LLM timeout
            with patch(
                "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm"
            ) as mock_llm:
                mock_llm_instance = AsyncMock()
                mock_llm_instance.ainvoke.side_effect = TimeoutError("Request timeout")
                mock_llm.return_value = (mock_llm_instance, None)

                query = "artificial intelligence"

                results = await service.retrieve_relevant_documents(invocation_id, query)

                # Should return exactly 1 document matched by KeywordRelevancyChecker
                assert len(results) == 1, f"Expected exactly 1 document from keyword fallback, got {len(results)}"

                # The single result should have fallback metadata indicating keyword fallback was used
                doc = results[0]
                assert doc.retrieval_metadata["primary_checker_failed"] is True
                assert doc.retrieval_metadata["relevancy_checker_used"] == "fallback"
                assert doc.retrieval_metadata["relevancy_checker_type"] == "keyword"

                # Document should contain content that matches the query "artificial intelligence"
                assert "artificial" in doc.content.lower() or "intelligence" in doc.content.lower()

                # Document should have a relevancy score from keyword matching
                assert doc.relevancy_score > 0.0, "Keyword fallback should assign non-zero relevancy score"

    @pytest.mark.asyncio
    async def test_partial_llm_failure_mixed_results(
        self,
        configured_retriever_registry: RetrieverRegistry,
        configured_relevancy_registry: RelevancyRegistry,
        mock_file_manager: MagicMock,
    ) -> None:
        """Test handling when LLM fails for some documents but not others."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create multiple test documents using helper function
            file_metadata1 = create_file_metadata_with_content(
                temp_path, "doc1", "First document about Python programming."
            )
            file_metadata2 = create_file_metadata_with_content(temp_path, "doc2", "Second document about data science.")

            # Set up mock FileManager for TestUploadedFileRetriever
            file_ids = (file_metadata1.id, file_metadata2.id)
            mock_file_manager._test_file_metadata_store[file_ids] = [file_metadata1, file_metadata2]
            TestUploadedFileRetriever._test_file_manager = mock_file_manager

            # Setup mock session and invocation
            mock_session = MagicMock(spec=AsyncSession)
            invocation_id = uuid4()
            mock_invocation = Invocation(
                id=invocation_id,
                prompt="test prompt",
                session_id="test_session",
                context_data={CONTEXT_KEY_FILE_IDS: [str(fid) for fid in file_ids]},
            )
            mock_session.get.return_value = mock_invocation

            # Create service with configured registries
            service = RetrieverService(
                session_factory=lambda: async_session_generator(mock_session),
                retriever_registry_factory=lambda: configured_retriever_registry,
                relevancy_registry_factory=lambda: configured_relevancy_registry,
            )

            # For this test, we'll simply mock LLM failure for all documents to ensure fallback behavior
            with patch(
                "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm"
            ) as mock_llm:
                # Mock LLM completely unavailable to trigger fallback for all documents
                mock_llm.side_effect = Exception("LLM service completely unavailable")

                query = "Python programming"

                results = await service.retrieve_relevant_documents(invocation_id, query)

                # Should return only 1 document - the relevant one that matches "Python programming"
                assert len(results) == 1, f"Expected exactly 1 relevant document through fallback, got {len(results)}"

                # The result should be fallback result since LLM is completely unavailable
                doc = results[0]
                assert doc.retrieval_metadata["primary_checker_failed"] is True
                assert doc.retrieval_metadata["relevancy_checker_used"] == "fallback"
                assert doc.retrieval_metadata["relevancy_checker_type"] == "keyword"

                # The returned document should contain relevant content for "Python programming"
                assert "python" in doc.content.lower(), "Document should contain 'python'"
                assert "programming" in doc.content.lower(), "Document should contain 'programming'"

    @pytest.mark.asyncio
    async def test_keyword_fallback_maintains_functionality(
        self,
        configured_retriever_registry: RetrieverRegistry,
        configured_relevancy_registry: RelevancyRegistry,
        mock_file_manager: MagicMock,
    ) -> None:
        """Test that keyword fallback provides reasonable relevancy scoring."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create documents with clear keyword relevancy differences using helper function
            relevant_metadata = create_file_metadata_with_content(
                temp_path, "python_tutorial", "Python programming language tutorial with examples and syntax."
            )
            irrelevant_metadata = create_file_metadata_with_content(
                temp_path, "cooking_recipes", "Cooking recipes for delicious Italian pasta dishes."
            )

            # Set up mock FileManager for TestUploadedFileRetriever
            file_ids = (relevant_metadata.id, irrelevant_metadata.id)
            mock_file_manager._test_file_metadata_store[file_ids] = [relevant_metadata, irrelevant_metadata]
            TestUploadedFileRetriever._test_file_manager = mock_file_manager

            # Setup mock session and invocation
            mock_session = MagicMock(spec=AsyncSession)
            invocation_id = uuid4()
            mock_invocation = Invocation(
                id=invocation_id,
                prompt="test prompt",
                session_id="test_session",
                context_data={CONTEXT_KEY_FILE_IDS: [str(fid) for fid in file_ids]},
            )
            mock_session.get.return_value = mock_invocation

            # Create service with configured registries
            service = RetrieverService(
                session_factory=lambda: async_session_generator(mock_session),
                retriever_registry_factory=lambda: configured_retriever_registry,
                relevancy_registry_factory=lambda: configured_relevancy_registry,
            )

            # Force LLM failure to test keyword fallback exclusively
            with patch(
                "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm"
            ) as mock_llm:
                mock_llm.side_effect = Exception("Forced LLM failure for testing")

                query = "Python programming"

                results = await service.retrieve_relevant_documents(invocation_id, query)

                # Should return at least the relevant document (Python tutorial)
                assert len(results) == 1, f"Expected exactly 1 relevant document through fallback, got {len(results)}"

                # The result should be fallback result since LLM is completely unavailable
                doc = results[0]
                assert doc.retrieval_metadata["primary_checker_failed"] is True
                assert doc.retrieval_metadata["relevancy_checker_used"] == "fallback"
                assert doc.retrieval_metadata["relevancy_checker_type"] == "keyword"

                # The returned document should contain relevant content for "Python programming"
                assert "python" in doc.content.lower(), "Document should contain 'python'"
                assert "programming" in doc.content.lower(), "Document should contain 'programming'"

    @pytest.mark.asyncio
    async def test_no_fallback_checker_available_error_handling(
        self,
        configured_retriever_registry: RetrieverRegistry,
        configured_relevancy_registry_llm_only: RelevancyRegistry,
    ) -> None:
        """Test error handling when no fallback checker is available."""
        # Setup mock session and invocation
        mock_session = MagicMock(spec=AsyncSession)
        invocation_id = uuid4()
        mock_invocation = Invocation(id=invocation_id, prompt="test prompt", session_id="test_session", context_data={})
        mock_session.get.return_value = mock_invocation

        # Create service with LLM-only registry (no fallback)
        service = RetrieverService(
            session_factory=lambda: async_session_generator(mock_session),
            retriever_registry_factory=lambda: configured_retriever_registry,
            relevancy_registry_factory=lambda: configured_relevancy_registry_llm_only,
        )

        # Force LLM failure with no fallback available
        with patch(
            "syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker.get_openrouter_llm"
        ) as mock_llm:
            mock_llm.side_effect = Exception("LLM failure")

            query = "test query"

            # Should gracefully return empty results when no fallback is available
            results = await service.retrieve_relevant_documents(invocation_id, query)
            assert results == [], f"Expected empty results when no fallback available, got {len(results)} results"
