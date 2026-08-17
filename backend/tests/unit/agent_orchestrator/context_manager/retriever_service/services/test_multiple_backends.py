"""Integration tests for multiple storage backend collation.

This module tests the RetrieverService's ability to collate documents from
multiple registered storage backends and provide unified relevancy scoring.
"""

from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.context_manager.retriever_service.exceptions import DocumentRetrievalError
from syntara.agent_orchestrator.context_manager.retriever_service.interfaces.document_retriever import DocumentRetriever
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument
from syntara.agent_orchestrator.context_manager.retriever_service.registries.relevancy_registry import RelevancyRegistry
from syntara.agent_orchestrator.context_manager.retriever_service.registries.retriever_registry import RetrieverRegistry
from syntara.agent_orchestrator.context_manager.retriever_service.services.retriever_service import RetrieverService
from syntara.agent_orchestrator.models.invocation import Invocation
from syntara.files.models import FileMetadata


class MockRetrieverError(Exception):
    """Custom exception for test retriever failures."""


async def async_session_generator(session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Create an async generator for the session factory."""
    yield session


# Mock storage backend retriever for testing
class MockDocumentRetriever(DocumentRetriever):
    """Mock implementation of document retriever for any backend type."""

    def __init__(self, mock_documents: list[RelevantDocument] | None = None) -> None:
        """Initialize mock document retriever.

        Args:
            mock_documents: Optional list of mock documents to return

        """
        self.mock_documents = mock_documents or []

    def retrieve_documents(self, _invocation_context: dict[str, Any]) -> AsyncIterator[RelevantDocument]:
        """Return mock documents."""
        return self._mock_documents_async_iterator()

    async def _mock_documents_async_iterator(self) -> AsyncIterator[RelevantDocument]:
        """Return mock documents as async iterator."""
        for document in self.mock_documents:
            yield document


@pytest.mark.integration
class TestMultipleStorageBackendCollation:
    """Integration tests for multiple storage backend coordination."""

    @pytest.mark.asyncio
    async def test_collate_documents_from_all_registered_backends(self) -> None:
        """Test that RetrieverService uses ALL registered retrievers."""
        # Create mock documents for each backend
        file_metadata_1 = FileMetadata(
            file_id=str(uuid4()),
            filename="uploaded_doc.pdf",
            size_bytes=1024,
            mime_type="application/pdf",
            file_path="/uploads/uploaded_doc.pdf",
            status="converted",
        )

        uploaded_doc = RelevantDocument(
            content="Document from uploaded files storage",
            relevancy_score=1.0,
            file_metadata=file_metadata_1,
            source_type="uploaded_file",
            retrieval_metadata={"backend": "uploaded_files"},
        )

        database_doc = RelevantDocument(
            content="Document from database storage",
            relevancy_score=1.0,
            file_metadata=file_metadata_1,  # Reuse for simplicity
            source_type="database",
            retrieval_metadata={"backend": "database"},
        )

        cloud_doc = RelevantDocument(
            content="Document from cloud storage",
            relevancy_score=1.0,
            file_metadata=file_metadata_1,  # Reuse for simplicity
            source_type="cloud_storage",
            retrieval_metadata={"backend": "cloud_storage"},
        )

        # Setup registry with multiple retrievers
        retriever_registry = RetrieverRegistry()
        relevancy_registry = RelevancyRegistry()

        # Create specific test retriever classes with test data
        class TestUploadedFileRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__([uploaded_doc])

        class TestDatabaseRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__([database_doc])

        class TestCloudStorageRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__([cloud_doc])

        # Register all three backend retrievers with test data
        retriever_registry.register_retriever("uploaded_file", TestUploadedFileRetriever)
        retriever_registry.register_retriever("database", TestDatabaseRetriever)
        retriever_registry.register_retriever("cloud_storage", TestCloudStorageRetriever)

        # Create service
        mock_session = MagicMock(spec=AsyncSession)

        # Create mock invocation with file metadata for retrievers to use
        invocation_id = uuid4()
        mock_invocation = Invocation(
            id=invocation_id,
            prompt="test prompt",
            session_id="test_session",
            context_data={
                "file_metadata": [
                    file_metadata_1.model_dump(),  # Include the file metadata
                ]
            },
        )

        # Configure the mock session to return the mock invocation
        mock_session.get.return_value = mock_invocation

        service = RetrieverService(
            session_factory=lambda: async_session_generator(mock_session),
            retriever_registry_factory=lambda: retriever_registry,
            relevancy_registry_factory=lambda: relevancy_registry,
        )

        # Execute retrieval
        query = "test query for all backends"

        results = await service.retrieve_relevant_documents(invocation_id, query)

        # Should return documents from all three backends
        source_types = {doc.source_type for doc in results}
        assert "uploaded_file" in source_types
        assert "database" in source_types
        assert "cloud_storage" in source_types

        # Verify content from each backend
        contents = {doc.content for doc in results}
        assert "Document from uploaded files storage" in contents
        assert "Document from database storage" in contents
        assert "Document from cloud storage" in contents

    @pytest.mark.asyncio
    async def test_unified_relevancy_scoring_across_backends(self) -> None:
        """Test unified relevancy scoring for documents from different backends."""
        # Create documents with different content relevancy
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="test_doc.pdf",
            size_bytes=1024,
            mime_type="application/pdf",
            file_path="/test/doc.pdf",
            status="converted",
        )

        highly_relevant_uploaded = RelevantDocument(
            content="Python programming tutorial with comprehensive examples and best practices",
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )

        somewhat_relevant_database = RelevantDocument(
            content="Programming concepts and software development methodologies overview",
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="database",
            retrieval_metadata={},
        )

        less_relevant_cloud = RelevantDocument(
            content="General technology trends and industry analysis report",
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="cloud_storage",
            retrieval_metadata={},
        )

        # Setup service with mock retrievers
        retriever_registry = RetrieverRegistry()
        relevancy_registry = RelevancyRegistry()

        # Create specific test retriever classes with test data
        class TestUploadedFileRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__([highly_relevant_uploaded])

        class TestDatabaseRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__([somewhat_relevant_database])

        class TestCloudStorageRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__([less_relevant_cloud])

        # Register all three backend retrievers with test data
        retriever_registry.register_retriever("uploaded_file", TestUploadedFileRetriever)
        retriever_registry.register_retriever("database", TestDatabaseRetriever)
        retriever_registry.register_retriever("cloud_storage", TestCloudStorageRetriever)

        mock_session = MagicMock(spec=AsyncSession)

        # Create mock invocation with file metadata for retrievers to use
        invocation_id = uuid4()
        mock_invocation = Invocation(
            id=invocation_id,
            prompt="test prompt",
            session_id="test_session",
            context_data={
                "file_metadata": [
                    file_metadata.model_dump(),  # Include the file metadata
                ]
            },
        )

        # Configure the mock session to return the mock invocation
        mock_session.get.return_value = mock_invocation

        service = RetrieverService(
            session_factory=lambda: async_session_generator(mock_session),
            retriever_registry_factory=lambda: retriever_registry,
            relevancy_registry_factory=lambda: relevancy_registry,
        )

        query = "Python programming tutorial"
        results = await service.retrieve_relevant_documents(invocation_id, query)

        # Should return all 3 documents from different backends
        assert len(results) == 3, f"Expected exactly 3 documents from all backends, got {len(results)}"

        # Verify we have documents from all three source types
        source_types = {doc.source_type for doc in results}
        assert source_types == {"uploaded_file", "database", "cloud_storage"}

        # Results should be ranked by relevancy score (all have default scores)
        for i in range(len(results) - 1):
            assert results[i].relevancy_score >= results[i + 1].relevancy_score

        # Find the Python tutorial document (should be most relevant)
        python_docs = [doc for doc in results if "Python" in doc.content]
        assert len(python_docs) == 1, "Should find exactly one Python tutorial document"
        python_doc = python_docs[0]
        assert python_doc.source_type == "uploaded_file"

        # Find the programming document
        programming_docs = [doc for doc in results if "Programming concepts" in doc.content]
        assert len(programming_docs) == 1, "Should find exactly one programming concepts document"
        programming_doc = programming_docs[0]
        assert programming_doc.source_type == "database"

        # Find the general tech document
        tech_docs = [doc for doc in results if "technology trends" in doc.content]
        assert len(tech_docs) == 1, "Should find exactly one technology trends document"
        tech_doc = tech_docs[0]
        assert tech_doc.source_type == "cloud_storage"

    @pytest.mark.asyncio
    async def test_backend_failure_causes_invocation_failure(self) -> None:
        """Test that failure in any backend causes entire invocation to fail (fail-fast behavior)."""
        # Create working retrievers and one failing retriever
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="working_doc.pdf",
            size_bytes=512,
            mime_type="application/pdf",
            file_path="/test/working_doc.pdf",
            status="converted",
        )

        working_doc = RelevantDocument(
            content="Document from working backend",
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )

        class FailingRetriever(DocumentRetriever):
            def retrieve_documents(self, _invocation_context: dict[str, Any]) -> AsyncIterator[RelevantDocument]:
                msg = "Backend failure simulation"
                raise MockRetrieverError(msg)

        # Setup service with one failing and one working retriever
        retriever_registry = RetrieverRegistry()
        relevancy_registry = RelevancyRegistry()

        # Create specific test retriever classes with test data
        class TestWorkingRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__([working_doc])

        retriever_registry.register_retriever("uploaded_file", TestWorkingRetriever)
        retriever_registry.register_retriever("failing_backend", FailingRetriever)

        mock_session = MagicMock(spec=AsyncSession)

        # Create mock invocation with file metadata for retrievers to use
        invocation_id = uuid4()
        mock_invocation = Invocation(
            id=invocation_id,
            prompt="test prompt",
            session_id="test_session",
            context_data={
                "file_metadata": [
                    file_metadata.model_dump(),  # Include the file metadata
                ]
            },
        )

        # Configure the mock session to return the mock invocation
        mock_session.get.return_value = mock_invocation

        service = RetrieverService(
            session_factory=lambda: async_session_generator(mock_session),
            retriever_registry_factory=lambda: retriever_registry,
            relevancy_registry_factory=lambda: relevancy_registry,
        )

        query = "test query"

        # With fail-fast behavior, ANY backend failure should fail the entire invocation
        with pytest.raises(DocumentRetrievalError) as exc_info:
            await service.retrieve_relevant_documents(invocation_id, query)

        assert "Failed to retrieve document" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_backend_handling(self) -> None:
        """Test handling when some backends return no documents."""
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="single_doc.pdf",
            size_bytes=256,
            mime_type="application/pdf",
            file_path="/single/doc.pdf",
            status="converted",
        )

        single_doc = RelevantDocument(
            content="Only document from one backend",
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={},
        )

        # Setup with one populated and two empty retrievers
        retriever_registry = RetrieverRegistry()
        relevancy_registry = RelevancyRegistry()

        # Create specific test retriever classes with test data
        class TestPopulatedRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__([single_doc])

        class TestEmptyDatabaseRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__([])  # Empty

        class TestEmptyCloudRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__([])  # Empty

        retriever_registry.register_retriever("uploaded_file", TestPopulatedRetriever)
        retriever_registry.register_retriever("database", TestEmptyDatabaseRetriever)
        retriever_registry.register_retriever("cloud_storage", TestEmptyCloudRetriever)

        mock_session = MagicMock(spec=AsyncSession)

        # Create mock invocation with file metadata for retrievers to use
        invocation_id = uuid4()
        mock_invocation = Invocation(
            id=invocation_id,
            prompt="test prompt",
            session_id="test_session",
            context_data={
                "file_metadata": [
                    file_metadata.model_dump(),  # Include the file metadata
                ]
            },
        )

        # Configure the mock session to return the mock invocation
        mock_session.get.return_value = mock_invocation

        service = RetrieverService(
            session_factory=lambda: async_session_generator(mock_session),
            retriever_registry_factory=lambda: retriever_registry,
            relevancy_registry_factory=lambda: relevancy_registry,
        )

        query = "test query"

        results = await service.retrieve_relevant_documents(invocation_id, query)

        # Should return documents from populated backend only
        assert len(results) == 1
        assert results[0].content == "Only document from one backend"
        assert results[0].source_type == "uploaded_file"

    @pytest.mark.asyncio
    async def test_large_scale_multi_backend_coordination(self) -> None:
        """Test coordination with many documents across multiple backends."""
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="bulk_test.pdf",
            size_bytes=1024,
            mime_type="application/pdf",
            file_path="/bulk/test.pdf",
            status="converted",
        )

        # Create multiple documents for each backend
        uploaded_docs = []
        database_docs = []
        cloud_docs = []

        for i in range(5):
            uploaded_docs.append(
                RelevantDocument(
                    content=f"Uploaded document {i} about machine learning",
                    relevancy_score=1.0,
                    file_metadata=file_metadata,
                    source_type="uploaded_file",
                    retrieval_metadata={"doc_id": i},
                )
            )

            database_docs.append(
                RelevantDocument(
                    content=f"Database document {i} about data processing",
                    relevancy_score=1.0,
                    file_metadata=file_metadata,
                    source_type="database",
                    retrieval_metadata={"doc_id": i},
                )
            )

            cloud_docs.append(
                RelevantDocument(
                    content=f"Cloud document {i} about artificial intelligence",
                    relevancy_score=1.0,
                    file_metadata=file_metadata,
                    source_type="cloud_storage",
                    retrieval_metadata={"doc_id": i},
                )
            )

        # Setup service with all documents
        retriever_registry = RetrieverRegistry()
        relevancy_registry = RelevancyRegistry()

        # Create specific test retriever classes with test data
        class TestUploadedFileRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__(uploaded_docs)

        class TestDatabaseRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__(database_docs)

        class TestCloudStorageRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__(cloud_docs)

        # Register all three backend retrievers with bulk test data
        retriever_registry.register_retriever("uploaded_file", TestUploadedFileRetriever)
        retriever_registry.register_retriever("database", TestDatabaseRetriever)
        retriever_registry.register_retriever("cloud_storage", TestCloudStorageRetriever)

        mock_session = MagicMock(spec=AsyncSession)

        # Create mock invocation with file metadata for retrievers to use
        invocation_id = uuid4()
        mock_invocation = Invocation(
            id=invocation_id,
            prompt="test prompt",
            session_id="test_session",
            context_data={
                "file_metadata": [
                    file_metadata.model_dump(),  # Include the file metadata
                ]
            },
        )

        # Configure the mock session to return the mock invocation
        mock_session.get.return_value = mock_invocation

        service = RetrieverService(
            session_factory=lambda: async_session_generator(mock_session),
            retriever_registry_factory=lambda: retriever_registry,
            relevancy_registry_factory=lambda: relevancy_registry,
        )

        query = "machine learning artificial intelligence"

        results = await service.retrieve_relevant_documents(invocation_id, query)

        # Should return all 15 documents (5 from each backend)
        assert len(results) == 15, f"Expected exactly 15 documents from all backends, got {len(results)}"

        # Should have documents from all three backends
        source_types = {doc.source_type for doc in results}
        assert source_types == {"uploaded_file", "database", "cloud_storage"}

        # Verify exact counts per backend
        uploaded_results = [doc for doc in results if doc.source_type == "uploaded_file"]
        database_results = [doc for doc in results if doc.source_type == "database"]
        cloud_results = [doc for doc in results if doc.source_type == "cloud_storage"]

        assert len(uploaded_results) == 5, f"Expected 5 uploaded documents, got {len(uploaded_results)}"
        assert len(database_results) == 5, f"Expected 5 database documents, got {len(database_results)}"
        assert len(cloud_results) == 5, f"Expected 5 cloud documents, got {len(cloud_results)}"

        # Results should be properly ranked by relevancy score
        for i in range(len(results) - 1):
            assert results[i].relevancy_score >= results[i + 1].relevancy_score

        # Verify document IDs are preserved in retrieval metadata
        for doc in results:
            assert "doc_id" in doc.retrieval_metadata
            assert 0 <= doc.retrieval_metadata["doc_id"] <= 4

        # Verify content patterns per backend
        for doc in uploaded_results:
            assert "machine learning" in doc.content
            assert "Uploaded document" in doc.content

        for doc in database_results:
            assert "data processing" in doc.content
            assert "Database document" in doc.content

        for doc in cloud_results:
            assert "artificial intelligence" in doc.content
            assert "Cloud document" in doc.content

    @pytest.mark.asyncio
    async def test_backend_specific_metadata_preservation(self) -> None:
        """Test that backend-specific metadata is preserved during collation."""
        file_metadata = FileMetadata(
            file_id=str(uuid4()),
            filename="metadata_test.pdf",
            size_bytes=512,
            mime_type="application/pdf",
            file_path="/metadata/test.pdf",
            status="converted",
        )

        # Create documents with backend-specific metadata
        uploaded_doc = RelevantDocument(
            content="Uploaded document with specific metadata",
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="uploaded_file",
            retrieval_metadata={"upload_time": "2023-01-01T12:00:00Z", "file_size_mb": 2.5, "uploader_id": "user123"},
        )

        database_doc = RelevantDocument(
            content="Database document with query metadata",
            relevancy_score=1.0,
            file_metadata=file_metadata,
            source_type="database",
            retrieval_metadata={"table_name": "documents", "row_id": 42, "last_modified": "2023-01-02T08:30:00Z"},
        )

        # Setup service
        retriever_registry = RetrieverRegistry()
        relevancy_registry = RelevancyRegistry()

        # Create specific test retriever classes with test data
        class TestUploadedFileRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__([uploaded_doc])

        class TestDatabaseRetriever(MockDocumentRetriever):
            def __init__(self) -> None:
                super().__init__([database_doc])

        # Register both backend retrievers with test data
        retriever_registry.register_retriever("uploaded_file", TestUploadedFileRetriever)
        retriever_registry.register_retriever("database", TestDatabaseRetriever)

        mock_session = MagicMock(spec=AsyncSession)

        # Create mock invocation with file metadata for retrievers to use
        invocation_id = uuid4()
        mock_invocation = Invocation(
            id=invocation_id,
            prompt="test prompt",
            session_id="test_session",
            context_data={
                "file_metadata": [
                    file_metadata.model_dump(),  # Include the file metadata
                ]
            },
        )

        # Configure the mock session to return the mock invocation
        mock_session.get.return_value = mock_invocation

        service = RetrieverService(
            session_factory=lambda: async_session_generator(mock_session),
            retriever_registry_factory=lambda: retriever_registry,
            relevancy_registry_factory=lambda: relevancy_registry,
        )

        query = "metadata test"
        results = await service.retrieve_relevant_documents(invocation_id, query)

        # Should return exactly 2 documents (one from each backend)
        assert len(results) == 2, f"Expected exactly 2 documents from both backends, got {len(results)}"

        # Verify backend-specific metadata is preserved
        uploaded_results = [doc for doc in results if doc.source_type == "uploaded_file"]
        database_results = [doc for doc in results if doc.source_type == "database"]

        # Should have exactly one document from each backend
        assert len(uploaded_results) == 1, f"Expected 1 uploaded document, got {len(uploaded_results)}"
        assert len(database_results) == 1, f"Expected 1 database document, got {len(database_results)}"

        # Verify uploaded file metadata is preserved
        uploaded_meta = uploaded_results[0].retrieval_metadata
        assert uploaded_meta["uploader_id"] == "user123", "Upload metadata should preserve uploader_id"
        assert uploaded_meta["file_size_mb"] == pytest.approx(2.5), "Upload metadata should preserve file_size_mb"
        assert uploaded_meta["upload_time"] == "2023-01-01T12:00:00Z", "Upload metadata should preserve upload_time"

        # Verify content matches
        assert "Uploaded document with specific metadata" in uploaded_results[0].content

        # Verify database metadata is preserved
        database_meta = database_results[0].retrieval_metadata
        assert database_meta["table_name"] == "documents", "Database metadata should preserve table_name"
        assert database_meta["row_id"] == 42, "Database metadata should preserve row_id"
        assert database_meta["last_modified"] == "2023-01-02T08:30:00Z", (
            "Database metadata should preserve last_modified"
        )

        # Verify content matches
        assert "Database document with query metadata" in database_results[0].content

        # Verify that each document retains its source type
        assert uploaded_results[0].source_type == "uploaded_file"
        assert database_results[0].source_type == "database"

    @pytest.mark.asyncio
    async def test_no_registered_backends_handling(self) -> None:
        """Test handling when no retriever backends are registered."""
        # Setup service with empty registry
        retriever_registry = RetrieverRegistry()
        relevancy_registry = RelevancyRegistry()

        mock_session = MagicMock(spec=AsyncSession)

        # Create mock invocation (empty context is fine for this test)
        invocation_id = uuid4()
        mock_invocation = Invocation(
            id=invocation_id,
            prompt="test prompt",
            session_id="test_session",
            context_data={},  # Empty context data
        )

        # Configure the mock session to return the mock invocation
        mock_session.get.return_value = mock_invocation

        service = RetrieverService(
            session_factory=lambda: async_session_generator(mock_session),
            retriever_registry_factory=lambda: retriever_registry,
            relevancy_registry_factory=lambda: relevancy_registry,
        )

        query = "test query with no backends"

        results = await service.retrieve_relevant_documents(invocation_id, query)

        # Should return empty list gracefully
        assert results == []
        assert isinstance(results, list)
