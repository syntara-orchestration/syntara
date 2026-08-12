"""Integration tests for RetrieverService main flow.

This module tests the complete end-to-end flow of the RetrieverService,
including document retrieval, relevancy checking, ranking, and filtering.
"""

import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.context_manager.retriever_service.exceptions import RetrieverServiceError
from syntara.agent_orchestrator.context_manager.retriever_service.interfaces.document_retriever import DocumentRetriever
from syntara.agent_orchestrator.context_manager.retriever_service.interfaces.relevancy_checker import RelevancyChecker
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevancy_configuration import (
    RelevancyConfiguration,
)
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument
from syntara.agent_orchestrator.context_manager.retriever_service.registries.relevancy_registry import RelevancyRegistry
from syntara.agent_orchestrator.context_manager.retriever_service.registries.retriever_registry import RetrieverRegistry
from syntara.agent_orchestrator.context_manager.retriever_service.services.retriever_service import RetrieverService
from syntara.agent_orchestrator.models.invocation import Invocation
from syntara.core.constants import CONTEXT_KEY_FILE_IDS
from syntara.files.models import FileMetadata, FileStatus

from .conftest import TestUploadedFileRetriever, async_session_generator


class MockRelevancyChecker(RelevancyChecker):
    """Mock relevancy checker that returns predictable scores for testing."""

    async def check_relevancy(
        self,
        document: RelevantDocument,
        _prompt: str,
        _config: RelevancyConfiguration,
        llm_credential_config: object = None,
    ) -> float:
        """Return mock scores based on document content for testing."""
        # Give high score to machine learning content, low score to gardening
        if "machine learning" in document.content.lower():
            return 0.9
        if "gardening" in document.content.lower():
            return 0.3
        return 0.5


class MockCloudStorageRetriever(DocumentRetriever):
    """Mock retriever simulating a cloud storage backend."""

    def retrieve_documents(self, _invocation_context: dict[str, Any]) -> AsyncIterator[RelevantDocument]:
        """Return mock documents from 'cloud storage'."""
        # Simulate retrieving documents from cloud storage
        # In real implementation, this would fetch from S3, Google Cloud Storage, etc.
        # This mock retriever always returns one cloud document regardless of invocation context
        return self._mock_cloud_async_iterator()

    async def _mock_cloud_async_iterator(self) -> AsyncIterator[RelevantDocument]:
        """Return mock cloud documents as async iterator."""
        # Create a dummy file metadata for cloud documents
        cloud_file_metadata = FileMetadata(
            id=uuid4(),
            filename="cloud_doc.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path="/cloud/path/cloud_doc.txt",
            status=FileStatus.CONVERTED,
            converted_content_path="/cloud/path/cloud_doc.txt",
        )

        yield RelevantDocument(
            content="Cloud-based machine learning platform documentation for distributed computing.",
            source_type="cloud_storage",
            file_metadata=cloud_file_metadata,
            retrieval_metadata={"backend": "mock_cloud", "source": "cloud_storage"},
            relevancy_score=0.0,  # Will be set by relevancy checker
        )


@pytest.mark.integration
class TestRetrieverServiceMainFlow:
    """Integration tests for complete RetrieverService flow."""

    @pytest.fixture
    def retriever_registry(self, mock_file_manager: MagicMock) -> RetrieverRegistry:
        """Provide a clean RetrieverRegistry with test uploaded file retriever registered."""
        registry = RetrieverRegistry()
        registry.register_retriever("uploaded_file", TestUploadedFileRetriever)
        TestUploadedFileRetriever._test_file_manager = mock_file_manager
        return registry

    @pytest.mark.asyncio
    async def test_end_to_end_document_retrieval_and_ranking(
        self, retriever_registry: RetrieverRegistry, mock_file_manager: MagicMock
    ) -> None:
        """Test complete flow from document retrieval to ranked results."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test documents with different relevancy to query
            highly_relevant = temp_path / "python_tutorial.txt"
            somewhat_relevant = temp_path / "programming_basics.txt"
            less_relevant = temp_path / "cooking_recipes.txt"

            highly_relevant.write_text(
                "Machine learning algorithms are computational methods that learn patterns from data.",
                encoding="utf-8",
            )
            somewhat_relevant.write_text(
                "Programming fundamentals include variables, loops, and functions. "
                "These concepts apply to many programming languages.",
                encoding="utf-8",
            )
            less_relevant.write_text(
                "Gardening tips for growing beautiful flowers in your backyard.",
                encoding="utf-8",
            )

            # Create file metadata for each document
            file_metadata_1 = FileMetadata(
                id=uuid4(),
                filename="python_tutorial.pdf",
                size_bytes=len(highly_relevant.read_text()),
                mime_type="application/pdf",
                file_path=str(temp_path / "python_tutorial.pdf"),
                status=FileStatus.CONVERTED,
                converted_content_path=str(highly_relevant),
            )

            file_metadata_2 = FileMetadata(
                id=uuid4(),
                filename="programming_basics.docx",
                size_bytes=len(somewhat_relevant.read_text()),
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                file_path=str(temp_path / "programming_basics.docx"),
                status=FileStatus.CONVERTED,
                converted_content_path=str(somewhat_relevant),
            )

            file_metadata_3 = FileMetadata(
                id=uuid4(),
                filename="cooking_recipes.txt",
                size_bytes=len(less_relevant.read_text()),
                mime_type="text/plain",
                file_path=str(temp_path / "cooking_recipes.txt"),
                status=FileStatus.CONVERTED,
                converted_content_path=str(less_relevant),
            )

            # Set up mock FileManager for TestUploadedFileRetriever
            file_ids = (file_metadata_1.id, file_metadata_2.id, file_metadata_3.id)
            mock_file_manager._test_file_metadata_store[file_ids] = [
                file_metadata_1,
                file_metadata_2,
                file_metadata_3,
            ]

            # Mock database session and invocation context
            mock_session = MagicMock(spec=AsyncSession)

            # Create a mock invocation with file_ids
            invocation_id = uuid4()
            mock_invocation = Invocation(
                id=invocation_id,
                prompt="test prompt",
                session_id="test_session",
                context_data={CONTEXT_KEY_FILE_IDS: [str(fid) for fid in file_ids]},
            )

            # Configure the mock session to return the mock invocation
            mock_session.get.return_value = mock_invocation

            # Use fixture-provided retriever_registry
            relevancy_registry = RelevancyRegistry()

            # Register configuration with low threshold using mock checker
            config = RelevancyConfiguration(
                checker_type="mock",
                similarity_threshold=0.2,  # Low threshold
                max_results=10,
                ranking_weights={},
                algorithm_parameters={},
                grounding_parameters={},
                recency_weight=0.1,
                mmr_settings={},
            )
            relevancy_registry.register_checker("mock", MockRelevancyChecker, config)

            # Create service instance
            service = RetrieverService(
                session_factory=lambda: async_session_generator(mock_session),
                retriever_registry_factory=lambda: retriever_registry,
                relevancy_registry_factory=lambda: relevancy_registry,
            )

            # Execute retrieval
            query = "Machine learning programming tutorial"
            results = await service.retrieve_relevant_documents(invocation_id, query)

            # Verify results are properly ranked by relevancy
            # Results should be sorted by relevancy score (highest first)
            assert len(results) == 3
            for i in range(len(results) - 1):
                assert results[i].relevancy_score >= results[i + 1].relevancy_score

            # Highly relevant document should score highest
            top_result = results[0]
            assert "Machine learning" in top_result.content

            # All results should have proper structure
            for doc in results:
                assert 0.0 <= doc.relevancy_score <= 1.0
                assert doc.source_type == "uploaded_file"
                assert doc.file_metadata is not None
                assert isinstance(doc.retrieval_metadata, dict)

    @pytest.mark.asyncio
    async def test_configuration_based_filtering(
        self, retriever_registry: RetrieverRegistry, mock_file_manager: MagicMock
    ) -> None:
        """Test filtering results based on configuration thresholds."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create one highly relevant and one irrelevant document
            relevant_doc = temp_path / "relevant.txt"
            irrelevant_doc = temp_path / "irrelevant.txt"

            relevant_doc.write_text(
                "Machine learning algorithms are computational methods that learn patterns from data.", encoding="utf-8"
            )
            irrelevant_doc.write_text(
                "Gardening tips for growing beautiful flowers in your backyard.", encoding="utf-8"
            )

            # Create file metadata for testing
            file_metadata_1 = FileMetadata(
                id=uuid4(),
                filename="ml_guide.pdf",
                size_bytes=len(relevant_doc.read_text()),
                mime_type="application/pdf",
                file_path=str(temp_path / "ml_guide.pdf"),
                status=FileStatus.CONVERTED,
                converted_content_path=str(relevant_doc),
            )

            file_metadata_2 = FileMetadata(
                id=uuid4(),
                filename="gardening.txt",
                size_bytes=len(irrelevant_doc.read_text()),
                mime_type="text/plain",
                file_path=str(temp_path / "gardening.txt"),
                status=FileStatus.CONVERTED,
                converted_content_path=str(irrelevant_doc),
            )

            # Set up mock FileManager for TestUploadedFileRetriever
            file_ids = (file_metadata_1.id, file_metadata_2.id)
            mock_file_manager._test_file_metadata_store[file_ids] = [
                file_metadata_1,
                file_metadata_2,
            ]

            # Test with high similarity threshold (should filter out irrelevant docs)
            mock_session = MagicMock(spec=AsyncSession)

            # Create a mock invocation with file_ids
            invocation_id = uuid4()
            mock_invocation = Invocation(
                id=invocation_id,
                prompt="test prompt",
                session_id="test_session",
                context_data={CONTEXT_KEY_FILE_IDS: [str(fid) for fid in file_ids]},
            )

            # Configure the mock session to return the mock invocation
            mock_session.get.return_value = mock_invocation

            # Use fixture-provided retriever_registry
            relevancy_registry = RelevancyRegistry()

            # Register configuration with high threshold using mock checker
            config = RelevancyConfiguration(
                checker_type="mock",
                similarity_threshold=0.7,  # High threshold
                max_results=10,
                ranking_weights={},
                algorithm_parameters={},
                grounding_parameters={},
                recency_weight=0.1,
                mmr_settings={},
            )
            relevancy_registry.register_checker("mock", MockRelevancyChecker, config)

            service = RetrieverService(
                session_factory=lambda: async_session_generator(mock_session),
                retriever_registry_factory=lambda: retriever_registry,
                relevancy_registry_factory=lambda: relevancy_registry,
            )

            # Use the same invocation_id from the mock
            query = "machine learning algorithms"
            results = await service.retrieve_relevant_documents(invocation_id, query)

            # With high threshold, should only return the relevant document
            assert len(results) == 1, f"Expected 1 result, got {len(results)}"

            # Should return the relevant document (file_metadata_1), not the irrelevant one
            returned_doc = results[0]
            assert returned_doc.relevancy_score >= 0.7
            assert returned_doc.file_metadata is not None
            assert returned_doc.file_metadata.filename == "ml_guide.pdf"
            assert "machine learning" in returned_doc.content.lower()

    @pytest.mark.asyncio
    async def test_max_results_limiting(
        self, retriever_registry: RetrieverRegistry, mock_file_manager: MagicMock
    ) -> None:
        """Test limiting results based on max_results configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create 5 documents
            documents = []
            file_metadata_list = []

            for i in range(5):
                doc_file = temp_path / f"document_{i}.txt"
                doc_file.write_text(
                    f"Document {i} about artificial intelligence and machine learning.", encoding="utf-8"
                )
                documents.append(doc_file)

                file_metadata = FileMetadata(
                    id=uuid4(),
                    filename=f"document_{i}.pdf",
                    size_bytes=len(doc_file.read_text()),
                    mime_type="application/pdf",
                    file_path=str(temp_path / f"document_{i}.pdf"),
                    status=FileStatus.CONVERTED,
                    converted_content_path=str(doc_file),
                )
                file_metadata_list.append(file_metadata)

            # Set up mock FileManager for TestUploadedFileRetriever
            file_ids = tuple(fm.id for fm in file_metadata_list)
            mock_file_manager._test_file_metadata_store[file_ids] = file_metadata_list

            # Test with max_results = 3
            mock_session = MagicMock(spec=AsyncSession)

            # Create a mock invocation with file_ids
            invocation_id = uuid4()
            mock_invocation = Invocation(
                id=invocation_id,
                prompt="test prompt",
                session_id="test_session",
                context_data={CONTEXT_KEY_FILE_IDS: [str(fid) for fid in file_ids]},
            )

            # Configure the mock session to return the mock invocation
            mock_session.get.return_value = mock_invocation

            # Use fixture-provided retriever_registry
            relevancy_registry = RelevancyRegistry()

            # Register configuration with max_results = 3 using mock checker
            config = RelevancyConfiguration(
                checker_type="mock",
                similarity_threshold=0.0,  # Low threshold to include all
                max_results=3,  # Limit to 3 results
                ranking_weights={},
                algorithm_parameters={},
                grounding_parameters={},
                recency_weight=0.1,
                mmr_settings={},
            )
            relevancy_registry.register_checker("mock", MockRelevancyChecker, config)

            service = RetrieverService(
                session_factory=lambda: async_session_generator(mock_session),
                retriever_registry_factory=lambda: retriever_registry,
                relevancy_registry_factory=lambda: relevancy_registry,
            )

            query = "artificial intelligence"
            results = await service.retrieve_relevant_documents(invocation_id, query)

            # Should return exactly 3 results (max_results limit)
            # All 5 documents contain "machine learning" so all get 0.9 score and pass 0.0 threshold
            # But max_results=3 should limit it to exactly 3 documents
            assert len(results) == 3, f"Expected exactly 3 results due to max_results limit, got {len(results)}"

            # All returned documents should have high relevancy scores from mock checker
            for doc in results:
                expected_score = 0.9
                actual_score = doc.relevancy_score
                assert actual_score == pytest.approx(expected_score), (
                    f"Expected score {expected_score}, got {actual_score}"
                )
                assert "machine learning" in doc.content.lower()
                assert doc.file_metadata is not None

            # Should be sorted by relevancy score (all equal in this case, so any order is valid)
            for i in range(len(results) - 1):
                assert results[i].relevancy_score >= results[i + 1].relevancy_score

    @pytest.mark.asyncio
    async def test_empty_invocation_handling(self, retriever_registry: RetrieverRegistry) -> None:
        """Test handling of invocation with no documents."""
        mock_session = MagicMock(spec=AsyncSession)

        # Use fixture-provided retriever_registry
        relevancy_registry = RelevancyRegistry()

        service = RetrieverService(
            session_factory=lambda: async_session_generator(mock_session),
            retriever_registry_factory=lambda: retriever_registry,
            relevancy_registry_factory=lambda: relevancy_registry,
        )

        # Mock invocation with no file metadata
        invocation_id = uuid4()
        mock_invocation = Invocation(
            id=invocation_id,
            prompt="test prompt",
            session_id="test_session",
            context_data={},  # Empty context data (no file_metadata)
        )

        # Configure the mock session to return the empty invocation
        mock_session.get.return_value = mock_invocation

        query = "test query"
        results = await service.retrieve_relevant_documents(invocation_id, query)

        # Should return empty list gracefully
        assert results == []
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_invalid_invocation_id_handling(self, retriever_registry: RetrieverRegistry) -> None:
        """Test handling of invalid invocation ID."""
        mock_session = MagicMock(spec=AsyncSession)

        # Use fixture-provided retriever_registry
        relevancy_registry = RelevancyRegistry()

        service = RetrieverService(
            session_factory=lambda: async_session_generator(mock_session),
            retriever_registry_factory=lambda: retriever_registry,
            relevancy_registry_factory=lambda: relevancy_registry,
        )

        # Use non-existent invocation ID
        invalid_invocation_id = uuid4()
        query = "test query"

        # Configure mock to return None for non-existent invocation
        mock_session.get.return_value = None

        # Should either return empty list or raise RetrieverServiceError
        # (Implementation will determine exact behavior)
        try:
            results = await service.retrieve_relevant_documents(invalid_invocation_id, query)
            assert results == []  # Graceful handling
        except RetrieverServiceError:
            pass  # Acceptable error handling

    @pytest.mark.asyncio
    async def test_dependency_injection_pattern(self, retriever_registry: RetrieverRegistry) -> None:
        """Test that RetrieverService properly uses dependency injection."""
        # Mock dependencies
        mock_session = MagicMock(spec=AsyncSession)

        # Use fixture-provided retriever_registry
        relevancy_registry = RelevancyRegistry()

        # Service should accept dependencies via constructor
        service = RetrieverService(
            session_factory=lambda: async_session_generator(mock_session),
            retriever_registry_factory=lambda: retriever_registry,
            relevancy_registry_factory=lambda: relevancy_registry,
        )

        # Verify dependencies are stored
        assert service.retriever_registry is retriever_registry
        assert service.relevancy_registry is relevancy_registry
        # Note: session is accessed via factory, not stored directly

    @pytest.mark.asyncio
    async def test_multiple_storage_backends_coordination(
        self, retriever_registry: RetrieverRegistry, mock_file_manager: MagicMock
    ) -> None:
        """Test coordination of multiple registered retrievers."""
        # This test verifies that RetrieverService uses ALL registered retrievers
        # to collate documents from different storage backends

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a file for the uploaded file retriever (default registry)
            uploaded_file = temp_path / "uploaded_doc.txt"
            uploaded_file.write_text("Uploaded file about machine learning and neural networks.", encoding="utf-8")

            # Create file metadata for uploaded file
            uploaded_file_metadata = FileMetadata(
                id=uuid4(),
                filename="uploaded_doc.pdf",
                size_bytes=len(uploaded_file.read_text()),
                mime_type="application/pdf",
                file_path=str(temp_path / "uploaded_doc.pdf"),
                status=FileStatus.CONVERTED,
                converted_content_path=str(uploaded_file),
            )

            # Set up mock FileManager for TestUploadedFileRetriever
            file_ids = (uploaded_file_metadata.id,)
            mock_file_manager._test_file_metadata_store[file_ids] = [uploaded_file_metadata]

            mock_session = MagicMock(spec=AsyncSession)

            # Create mock invocation with file_ids
            invocation_id = uuid4()
            mock_invocation = Invocation(
                id=invocation_id,
                prompt="test prompt",
                session_id="test_session",
                context_data={
                    CONTEXT_KEY_FILE_IDS: [str(fid) for fid in file_ids]
                    # Note: Cloud storage retriever ignores invocation context
                },
            )

            # Configure the mock session to return the mock invocation
            mock_session.get.return_value = mock_invocation

            # Use fixture-provided retriever_registry
            relevancy_registry = RelevancyRegistry()
            retriever_registry.register_retriever("cloud_storage", MockCloudStorageRetriever)

            # Register mock relevancy checker with low threshold to include all results
            config = RelevancyConfiguration(
                checker_type="mock",
                similarity_threshold=0.0,  # Include all documents
                max_results=10,
                ranking_weights={},
                algorithm_parameters={},
                grounding_parameters={},
                recency_weight=0.1,
                mmr_settings={},
            )
            relevancy_registry.register_checker("mock", MockRelevancyChecker, config)

            service = RetrieverService(
                session_factory=lambda: async_session_generator(mock_session),
                retriever_registry_factory=lambda: retriever_registry,
                relevancy_registry_factory=lambda: relevancy_registry,
            )

            query = "machine learning for multiple backends"
            results = await service.retrieve_relevant_documents(invocation_id, query)

            # Should return documents from BOTH backends
            # 1. UploadedFileRetriever should return the uploaded file
            # 2. MockCloudStorageRetriever should return the cloud document
            assert len(results) == 2, f"Expected documents from both backends, got {len(results)} results"

            # Verify we have documents from both source types
            source_types = {doc.source_type for doc in results}
            assert "uploaded_file" in source_types, "Missing document from uploaded_file backend"
            assert "cloud_storage" in source_types, "Missing document from cloud_storage backend"

            # All documents should have high relevancy scores (both contain "machine learning")
            for doc in results:
                expected_score = 0.9
                actual_score = doc.relevancy_score
                assert actual_score == pytest.approx(expected_score), (
                    f"Expected score {expected_score}, got {actual_score}"
                )
                assert "machine learning" in doc.content.lower()

            # Results should be sorted by relevancy score (equal scores, so any order is valid)
            for i in range(len(results) - 1):
                assert results[i].relevancy_score >= results[i + 1].relevancy_score

            # Verify backend-specific properties
            uploaded_doc = next((doc for doc in results if doc.source_type == "uploaded_file"), None)
            cloud_doc = next((doc for doc in results if doc.source_type == "cloud_storage"), None)

            assert uploaded_doc is not None, "UploadedFileRetriever document not found"
            assert cloud_doc is not None, "CloudStorageRetriever document not found"

            # Uploaded file should have proper file metadata
            assert uploaded_doc.file_metadata is not None
            assert uploaded_doc.file_metadata.filename == "uploaded_doc.pdf"

            # Cloud doc should have different retrieval metadata
            assert "backend" in cloud_doc.retrieval_metadata
            assert cloud_doc.retrieval_metadata["backend"] == "mock_cloud"

    @pytest.mark.asyncio
    async def test_cloud_storage_retrieval_with_none_invocation_id(self, retriever_registry: RetrieverRegistry) -> None:
        """Test cloud storage retrieval when invocation_id is None."""
        # This test verifies that when invocation_id is None, only cloud storage
        # retrievers work (those that don't depend on invocation context)
        # while uploaded file retrievers return nothing due to no context data

        mock_session = MagicMock(spec=AsyncSession)

        # Use fixture-provided retriever_registry
        relevancy_registry = RelevancyRegistry()
        retriever_registry.register_retriever("cloud_storage", MockCloudStorageRetriever)

        # Register mock relevancy checker with low threshold to include all results
        config = RelevancyConfiguration(
            checker_type="mock",
            similarity_threshold=0.0,  # Include all documents
            max_results=10,
            ranking_weights={},
            algorithm_parameters={},
            grounding_parameters={},
            recency_weight=0.1,
            mmr_settings={},
        )
        relevancy_registry.register_checker("mock", MockRelevancyChecker, config)

        service = RetrieverService(
            session_factory=lambda: async_session_generator(mock_session),
            retriever_registry_factory=lambda: retriever_registry,
            relevancy_registry_factory=lambda: relevancy_registry,
        )

        # Use None for invocation_id - no invocation context will be loaded
        query = "machine learning for cloud storage"
        results = await service.retrieve_relevant_documents(None, query)

        # Should return documents only from cloud storage backend
        # UploadedFileRetriever should return nothing due to empty invocation context
        # MockCloudStorageRetriever should return one cloud document
        assert len(results) == 1, f"Expected 1 document from cloud storage only, got {len(results)} results"

        # Verify we only have cloud storage documents
        source_types = {doc.source_type for doc in results}
        assert "cloud_storage" in source_types, "Missing document from cloud_storage backend"
        assert "uploaded_file" not in source_types, "Should not have uploaded_file documents when invocation_id is None"

        # The cloud document should have high relevancy score (contains "machine learning")
        cloud_doc = results[0]
        expected_score = 0.9
        actual_score = cloud_doc.relevancy_score
        assert actual_score == pytest.approx(expected_score), f"Expected score {expected_score}, got {actual_score}"
        assert "machine learning" in cloud_doc.content.lower()
        assert cloud_doc.source_type == "cloud_storage"

        # Verify cloud doc properties
        assert "backend" in cloud_doc.retrieval_metadata
        assert cloud_doc.retrieval_metadata["backend"] == "mock_cloud"
        assert cloud_doc.file_metadata is not None
        assert cloud_doc.file_metadata.filename == "cloud_doc.txt"
