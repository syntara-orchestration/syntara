"""Unit tests for UploadedFileRetriever.

This module tests UploadedFileRetriever's document retrieval logic with mocked FileManager,
ensuring proper validation, error handling, and edge case coverage.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.context_manager.retriever_service.exceptions import DocumentRetrievalError
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument
from syntara.agent_orchestrator.context_manager.retriever_service.retrievers.uploaded_file_retriever import (
    UploadedFileRetriever,
)
from syntara.files.models import FileMetadata, FileStatus


class TestUploadedFileRetriever:
    """Unit tests for UploadedFileRetriever with mocked FileManager."""

    @pytest.mark.asyncio
    async def test_retrieve_converted_documents(self, mock_session_factory, mock_file_manager) -> None:
        """Test retrieving documents from converted uploaded files."""
        # Setup temporary files for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a test converted file
            converted_file = temp_path / "converted_document.txt"
            test_content = "This is a test document with important information about machine learning algorithms."
            converted_file.write_text(test_content, encoding="utf-8")

            # Create file metadata as would be stored in database
            file_id = uuid4()
            file_metadata = FileMetadata(
                id=file_id,
                filename="original_document.pdf",
                size_bytes=1024,
                mime_type="application/pdf",
                file_path=str(temp_path / "original_document.pdf"),
                status=FileStatus.CONVERTED,
                converted_content_path=str(converted_file),
            )

            # Configure shared mock_file_manager to return the file metadata
            mock_file_manager._test_file_metadata_store[(file_id,)] = [file_metadata]

            # Setup invocation context with file_ids
            invocation_context = {"file_ids": [str(file_id)]}

            # Create UploadedFileRetriever instance
            retriever = UploadedFileRetriever(
                file_manager_factory=lambda: mock_file_manager,
                session_factory=mock_session_factory,
            )

            # Execute retrieval
            documents = [doc async for doc in retriever.retrieve_documents(invocation_context)]

            # Verify FileManager was called correctly
            mock_file_manager.get_files_metadata.assert_called_once()

            # Verify results
            assert len(documents) == 1
            doc = documents[0]
            assert isinstance(doc, RelevantDocument)
            assert doc.content == test_content
            assert doc.relevancy_score == pytest.approx(1.0)  # Initial neutral score
            assert doc.source_type == "uploaded_file"
            assert doc.file_metadata.id == file_metadata.id
            assert "retrieved_at" in doc.retrieval_metadata

    @pytest.mark.asyncio
    async def test_raise_error_for_unconverted_files(self, mock_session_factory, mock_file_manager) -> None:
        """Test that unconverted files raise DocumentRetrievalError."""
        # Create file metadata for unconverted file
        file_id = uuid4()
        pending_file = FileMetadata(
            id=file_id,
            filename="pending_document.pdf",
            size_bytes=512,
            mime_type="application/pdf",
            file_path="/path/to/pending.pdf",
            status=FileStatus.PENDING_CONVERSION,
        )

        # Configure shared mock_file_manager to return unconverted file
        mock_file_manager._test_file_metadata_store[(file_id,)] = [pending_file]

        invocation_context = {"file_ids": [str(file_id)]}

        retriever = UploadedFileRetriever(
            file_manager_factory=lambda: mock_file_manager,
            session_factory=mock_session_factory,
        )

        # Should raise DocumentRetrievalError with message including filename
        with pytest.raises(DocumentRetrievalError, match=r"Failed to retrieve file: pending_document\.pdf"):
            async for _ in retriever.retrieve_documents(invocation_context):
                pass

    @pytest.mark.asyncio
    async def test_raise_error_for_missing_files(self, mock_session_factory, mock_file_manager) -> None:
        """Test that missing file_ids raise DocumentRetrievalError."""
        file_id_1 = uuid4()
        file_id_2 = uuid4()  # This one won't be found

        # Mock FileManager to return only one file
        file_metadata_1 = FileMetadata(
            id=file_id_1,
            filename="found.pdf",
            size_bytes=1024,
            mime_type="application/pdf",
            file_path="/path/to/found.pdf",
            status=FileStatus.CONVERTED,
            converted_content_path="/path/to/converted.txt",
        )

        # Configure shared mock_file_manager to return only one file
        mock_file_manager._test_file_metadata_store[(file_id_1, file_id_2)] = [file_metadata_1]

        invocation_context = {"file_ids": [str(file_id_1), str(file_id_2)]}

        retriever = UploadedFileRetriever(
            file_manager_factory=lambda: mock_file_manager,
            session_factory=mock_session_factory,
        )

        with pytest.raises(DocumentRetrievalError, match="Failed to retrieve document"):
            async for _ in retriever.retrieve_documents(invocation_context):
                pass

    @pytest.mark.asyncio
    async def test_raise_error_for_non_string_items(self, mock_session_factory) -> None:
        """Test that non-string items in file_ids raise DocumentRetrievalError."""
        invocation_context = {"file_ids": [12345, None, "valid-uuid"]}  # Mixed types

        retriever = UploadedFileRetriever(
            session_factory=mock_session_factory,
        )

        # UUID() will raise TypeError for non-string types
        with pytest.raises(DocumentRetrievalError, match="Invalid UUID"):
            async for _ in retriever.retrieve_documents(invocation_context):
                pass

    @pytest.mark.asyncio
    async def test_raise_error_for_invalid_uuid_format(self, mock_session_factory) -> None:
        """Test that invalid UUID strings raise DocumentRetrievalError."""
        invocation_context = {"file_ids": ["not-a-uuid", "also-invalid"]}

        retriever = UploadedFileRetriever(
            session_factory=mock_session_factory,
        )

        with pytest.raises(DocumentRetrievalError, match="Invalid UUID"):
            async for _ in retriever.retrieve_documents(invocation_context):
                pass

    @pytest.mark.asyncio
    async def test_raise_error_for_invalid_type(self, mock_session_factory) -> None:
        """Test that non-list file_ids raise DocumentRetrievalError."""
        invocation_context = {"file_ids": "not-a-list"}  # String instead of list

        retriever = UploadedFileRetriever(
            session_factory=mock_session_factory,
        )

        with pytest.raises(DocumentRetrievalError, match="must be a list"):
            async for _ in retriever.retrieve_documents(invocation_context):
                pass

    @pytest.mark.asyncio
    async def test_database_error_propagation(self, mock_session_factory, mock_file_manager) -> None:
        """Test that database errors from FileManager are propagated correctly."""
        from sqlalchemy.exc import OperationalError

        file_id = uuid4()

        # Override get_files_metadata to raise database error
        mock_file_manager.get_files_metadata = AsyncMock(
            side_effect=OperationalError("connection refused", {}, Exception("connection refused"))
        )

        invocation_context = {"file_ids": [str(file_id)]}

        retriever = UploadedFileRetriever(
            file_manager_factory=lambda: mock_file_manager,
            session_factory=mock_session_factory,
        )

        # Database errors should propagate (not be caught/converted)
        with pytest.raises(OperationalError, match="connection refused"):
            async for _ in retriever.retrieve_documents(invocation_context):
                pass

    @pytest.mark.asyncio
    async def test_handle_missing_converted_file(self, mock_session_factory, mock_file_manager) -> None:
        """Test handling when converted file doesn't exist on disk - should fail fast."""
        file_id = uuid4()
        file_metadata = FileMetadata(
            id=file_id,
            filename="missing_converted.pdf",
            size_bytes=512,
            mime_type="application/pdf",
            file_path="/path/to/original.pdf",
            status=FileStatus.CONVERTED,
            converted_content_path="/nonexistent/converted.txt",
        )

        # Configure shared mock_file_manager to return the file metadata
        mock_file_manager._test_file_metadata_store[(file_id,)] = [file_metadata]

        invocation_context = {"file_ids": [str(file_id)]}

        retriever = UploadedFileRetriever(
            file_manager_factory=lambda: mock_file_manager,
            session_factory=mock_session_factory,
        )

        # Should fail fast with DocumentRetrievalError
        with pytest.raises(DocumentRetrievalError) as exc_info:
            async for _ in retriever.retrieve_documents(invocation_context):
                pass

        assert "Failed to retrieve file: missing_converted.pdf" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_invocation_context(self, mock_session_factory) -> None:
        """Test handling of empty invocation context."""
        retriever = UploadedFileRetriever(
            session_factory=mock_session_factory,
        )

        # Empty context
        documents = [doc async for doc in retriever.retrieve_documents({})]
        assert documents == []

        # Context with empty file_ids
        documents = [doc async for doc in retriever.retrieve_documents({"file_ids": []})]
        assert documents == []

    @pytest.mark.asyncio
    async def test_duplicate_file_ids_deduped(self, mock_session_factory, mock_file_manager) -> None:
        """Test that duplicate file_ids are silently deduplicated."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a test converted file
            converted_file = temp_path / "converted_document.txt"
            test_content = "This is a test document that appears in the request multiple times."
            converted_file.write_text(test_content, encoding="utf-8")

            # Create file metadata
            file_id = uuid4()
            file_metadata = FileMetadata(
                id=file_id,
                filename="document.pdf",
                size_bytes=1024,
                mime_type="application/pdf",
                file_path=str(temp_path / "document.pdf"),
                status=FileStatus.CONVERTED,
                converted_content_path=str(converted_file),
            )

            # Configure shared mock_file_manager to return the file metadata
            mock_file_manager._test_file_metadata_store[(file_id,)] = [file_metadata]

            # Request with duplicate file_ids
            invocation_context = {"file_ids": [str(file_id), str(file_id), str(file_id)]}

            # Create UploadedFileRetriever instance
            retriever = UploadedFileRetriever(
                file_manager_factory=lambda: mock_file_manager,
                session_factory=mock_session_factory,
            )

            # Execute retrieval
            documents = [doc async for doc in retriever.retrieve_documents(invocation_context)]

            # Verify FileManager was called with deduplicated list
            mock_file_manager.get_files_metadata.assert_called_once()
            called_file_ids = mock_file_manager.get_files_metadata.call_args[0][0]
            assert len(called_file_ids) == 1
            assert called_file_ids[0] == file_id

            # Verify results - should only return one document
            assert len(documents) == 1
            doc = documents[0]
            assert isinstance(doc, RelevantDocument)
            assert doc.content == test_content
            assert doc.file_metadata.id == file_metadata.id

    @pytest.mark.asyncio
    async def test_multiple_converted_files(self, mock_session_factory, mock_file_manager) -> None:
        """Test retrieving multiple converted files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create multiple test files
            file1 = temp_path / "doc1.txt"
            file2 = temp_path / "doc2.txt"
            file1.write_text("First document content", encoding="utf-8")
            file2.write_text("Second document content", encoding="utf-8")

            # Create metadata for multiple files
            file_id_1 = uuid4()
            file_id_2 = uuid4()

            file_metadata_1 = FileMetadata(
                id=file_id_1,
                filename="document1.pdf",
                size_bytes=1024,
                mime_type="application/pdf",
                file_path=str(temp_path / "document1.pdf"),
                status=FileStatus.CONVERTED,
                converted_content_path=str(file1),
            )

            file_metadata_2 = FileMetadata(
                id=file_id_2,
                filename="document2.docx",
                size_bytes=2048,
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                file_path=str(temp_path / "document2.docx"),
                status=FileStatus.CONVERTED,
                converted_content_path=str(file2),
            )

            # Configure shared mock_file_manager to return both file metadata
            mock_file_manager._test_file_metadata_store[(file_id_1, file_id_2)] = [file_metadata_1, file_metadata_2]

            invocation_context = {"file_ids": [str(file_id_1), str(file_id_2)]}

            retriever = UploadedFileRetriever(
                file_manager_factory=lambda: mock_file_manager,
                session_factory=mock_session_factory,
            )
            documents = [doc async for doc in retriever.retrieve_documents(invocation_context)]

            # Should return both documents
            assert len(documents) == 2

            # Verify both documents are properly created
            contents = {doc.content for doc in documents}
            assert "First document content" in contents
            assert "Second document content" in contents

            # All documents should have proper metadata
            for doc in documents:
                assert isinstance(doc, RelevantDocument)
                assert doc.relevancy_score == pytest.approx(1.0)
                assert doc.source_type == "uploaded_file"
                assert doc.file_metadata.status == FileStatus.CONVERTED

    @pytest.mark.asyncio
    async def test_file_manager_integration(self, mock_session_factory, mock_file_manager) -> None:
        """Test integration with FileManager through dependency injection."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_file = temp_path / "integration_test.txt"
            test_content = "Integration test content for FileManager"
            test_file.write_text(test_content, encoding="utf-8")

            file_id = uuid4()
            file_metadata = FileMetadata(
                id=file_id,
                filename="integration_test.pdf",
                size_bytes=len(test_content),
                mime_type="application/pdf",
                file_path=str(temp_path / "integration_test.pdf"),
                status=FileStatus.CONVERTED,
                converted_content_path=str(test_file),
            )

            # Configure shared mock_file_manager to return the file metadata
            mock_file_manager._test_file_metadata_store[(file_id,)] = [file_metadata]

            invocation_context = {"file_ids": [str(file_id)]}

            # Create retriever - it should internally use FileManager
            retriever = UploadedFileRetriever(
                file_manager_factory=lambda: mock_file_manager,
                session_factory=mock_session_factory,
            )
            documents = [doc async for doc in retriever.retrieve_documents(invocation_context)]

            assert len(documents) == 1
            doc = documents[0]
            assert doc.content == test_content

            # Verify retrieval metadata contains FileManager details
            assert doc.retrieval_metadata["file_path"] == str(test_file)
            assert "retrieved_at" in doc.retrieval_metadata
