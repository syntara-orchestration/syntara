"""Integration tests for UploadedFileRetriever with real database and FileManager.

This module tests UploadedFileRetriever with real database instances and FileManager,
ensuring proper end-to-end document retrieval without mocking core components.
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.context_manager.retriever_service.exceptions import DocumentRetrievalError
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument
from syntara.agent_orchestrator.context_manager.retriever_service.retrievers.uploaded_file_retriever import (
    UploadedFileRetriever,
)
from syntara.agent_orchestrator.context_manager.retriever_service.services.retriever_service import (
    get_retriever_service,
)
from syntara.agent_orchestrator.models.invocation import Invocation
from syntara.core.constants import CONTEXT_KEY_FILE_IDS
from syntara.files.file_manager import get_file_manager
from syntara.files.models import FileMetadata, FileStatus


@pytest.mark.integration
class TestUploadedFileRetrieverRealDatabaseIntegration:
    """Integration tests for UploadedFileRetriever with real database and FileManager."""

    @pytest.mark.asyncio
    async def test_retrieve_database_and_filemanager(
        self, test_db_session: AsyncSession, test_user, tmp_path: Path, test_project_id
    ) -> None:
        """Test retrieval with real database and FileManager.

        This validates:
        - FileMetadata stored in real database
        - Real FileManager queries database
        - Real file I/O from temp files
        - UploadedFileRetriever works end-to-end
        """
        test_content = "This is a test document about Python programming and machine learning algorithms."
        file_id = uuid4()

        file_manager = get_file_manager()
        s3 = file_manager.get_retriever()
        s3_path = f"nexus-{file_id}-test_document.txt"
        await s3.save_file(test_content.encode("utf-8"), s3_path)

        file_metadata = FileMetadata(
            id=file_id,
            filename="test_document.txt",
            size_bytes=len(test_content),
            mime_type="text/plain",
            file_path=s3_path,
            status=FileStatus.CONVERTED,
            converted_content_path=s3_path,
            created_by=test_user.id,
            project_id=test_project_id,
        )
        test_db_session.add(file_metadata)
        await test_db_session.commit()

        file_manager = get_file_manager()

        async def session_gen() -> AsyncGenerator[AsyncSession, None]:
            yield test_db_session

        retriever = UploadedFileRetriever(
            file_manager_factory=lambda: file_manager,
            session_factory=session_gen,
        )

        invocation_context = {CONTEXT_KEY_FILE_IDS: [str(file_id)]}

        documents = [doc async for doc in retriever.retrieve_documents(invocation_context)]

        assert len(documents) == 1
        doc = documents[0]
        assert isinstance(doc, RelevantDocument)
        assert doc.content == test_content
        assert doc.relevancy_score == pytest.approx(1.0)
        assert doc.source_type == "uploaded_file"
        assert doc.file_metadata.id == file_metadata.id
        assert doc.file_metadata.filename == "test_document.txt"
        assert "retrieved_at" in doc.retrieval_metadata

    @pytest.mark.asyncio
    async def test_converted_status_with_null_path_raises_error(
        self, test_db_session: AsyncSession, test_user, test_project_id
    ) -> None:
        """Test that CONVERTED status without converted_content_path raises DocumentRetrievalError."""
        file_id = uuid4()
        file_metadata = FileMetadata(
            id=file_id,
            filename="broken_file.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path="/path/to/original.txt",
            status=FileStatus.CONVERTED,
            converted_content_path=None,
            created_by=test_user.id,
            project_id=test_project_id,
        )
        test_db_session.add(file_metadata)
        await test_db_session.commit()

        file_manager = get_file_manager()

        async def session_gen() -> AsyncGenerator[AsyncSession, None]:
            yield test_db_session

        retriever = UploadedFileRetriever(
            file_manager_factory=lambda: file_manager,
            session_factory=session_gen,
        )

        invocation_context = {CONTEXT_KEY_FILE_IDS: [str(file_id)]}

        # CONVERTED status requires converted_content_path
        with pytest.raises(DocumentRetrievalError, match=r"Failed to retrieve file: broken_file\.txt"):
            async for _ in retriever.retrieve_documents(invocation_context):
                pass

    @pytest.mark.asyncio
    async def test_real_file_io_error_handling(self, test_db_session: AsyncSession, test_user, test_project_id) -> None:
        """Test handling of missing S3 objects with fail-fast behavior.

        This validates:
        - Missing S3 keys cause immediate failure
        - User-friendly error messages
        """
        file_id = uuid4()

        file_metadata = FileMetadata(
            id=file_id,
            filename="missing_file.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path="nexus-nonexistent-original.txt",
            status=FileStatus.CONVERTED,
            converted_content_path="nexus-nonexistent-does_not_exist.txt",
            created_by=test_user.id,
            project_id=test_project_id,
        )
        test_db_session.add(file_metadata)
        await test_db_session.commit()

        file_manager = get_file_manager()

        async def session_gen() -> AsyncGenerator[AsyncSession, None]:
            yield test_db_session

        retriever = UploadedFileRetriever(
            file_manager_factory=lambda: file_manager,
            session_factory=session_gen,
        )

        invocation_context = {CONTEXT_KEY_FILE_IDS: [str(file_id)]}

        with pytest.raises(DocumentRetrievalError, match=r"Failed to retrieve file: missing_file\.txt"):
            async for _ in retriever.retrieve_documents(invocation_context):
                pass

    @pytest.mark.asyncio
    async def test_exception_propagation_through_service_stack(
        self, test_db_session: AsyncSession, test_user, test_project_id
    ) -> None:
        """Test exception propagation through RetrieverService → UploadedFileRetriever → FileManager.

        This validates:
        - Real service instantiation
        - Real database queries
        - Real exception propagation with fail-fast behavior
        - User-friendly error messages
        """
        invalid_file_id = uuid4()  # File doesn't exist in database
        invocation = Invocation(
            prompt="Test prompt",
            session_id="test-session",
            status="created",
            context_data={CONTEXT_KEY_FILE_IDS: [str(invalid_file_id)]},
            created_by=test_user.id,
            project_id=test_project_id,
        )
        test_db_session.add(invocation)
        await test_db_session.commit()

        async def session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield test_db_session

        retriever_service = get_retriever_service(session_factory)

        # Call retrieve_relevant_documents - should fail fast with DocumentRetrievalError
        with pytest.raises(DocumentRetrievalError) as exc_info:
            await retriever_service.retrieve_relevant_documents(invocation.id, "Test query")

        error_message = str(exc_info.value)
        assert "Failed to retrieve document" in error_message
        assert str(invalid_file_id) not in error_message

    @pytest.mark.asyncio
    async def test_multiple_files_mixed_conversion_states(
        self, test_db_session: AsyncSession, test_user, tmp_path: Path, test_project_id
    ) -> None:
        """Test retrieval with multiple files in different states.

        This validates:
        - Batch file retrieval from database
        - Handling CONVERTED vs PENDING vs FAILED
        - Real FileManager batch operations
        """
        file_id_1 = uuid4()
        file_id_2 = uuid4()
        file_id_3 = uuid4()

        file_manager = get_file_manager()
        s3 = file_manager.get_retriever()
        s3_path = f"nexus-{file_id_1}-converted.txt"
        await s3.save_file(b"Valid content", s3_path)

        file_1 = FileMetadata(
            id=file_id_1,
            filename="converted.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path=s3_path,
            status=FileStatus.CONVERTED,
            converted_content_path=s3_path,
            created_by=test_user.id,
            project_id=test_project_id,
        )
        file_2 = FileMetadata(
            id=file_id_2,
            filename="pending.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path=str(tmp_path / "original2.txt"),
            status=FileStatus.PENDING_CONVERSION,
            created_by=test_user.id,
            project_id=test_project_id,
        )
        file_3 = FileMetadata(
            id=file_id_3,
            filename="failed.txt",
            size_bytes=100,
            mime_type="text/plain",
            file_path=str(tmp_path / "original3.txt"),
            status=FileStatus.CONVERSION_FAILED,
            conversion_error="Test error",
            created_by=test_user.id,
            project_id=test_project_id,
        )

        test_db_session.add_all([file_1, file_2, file_3])
        await test_db_session.commit()

        file_manager = get_file_manager()

        async def session_gen() -> AsyncGenerator[AsyncSession, None]:
            yield test_db_session

        retriever = UploadedFileRetriever(
            file_manager_factory=lambda: file_manager,
            session_factory=session_gen,
        )

        # Test 1: Request all 3 files - should raise error with message including all failed filenames
        invocation_context_all = {CONTEXT_KEY_FILE_IDS: [str(file_id_1), str(file_id_2), str(file_id_3)]}

        with pytest.raises(DocumentRetrievalError) as exc_info:
            async for _ in retriever.retrieve_documents(invocation_context_all):
                pass

        error_message = str(exc_info.value)
        assert "Failed to retrieve files:" in error_message
        assert "pending.txt" in error_message
        assert "failed.txt" in error_message

        # Test 2: Request only converted file - should succeed
        invocation_context_converted = {CONTEXT_KEY_FILE_IDS: [str(file_id_1)]}
        documents = [doc async for doc in retriever.retrieve_documents(invocation_context_converted)]

        assert len(documents) == 1
        assert documents[0].file_metadata.id == file_id_1
