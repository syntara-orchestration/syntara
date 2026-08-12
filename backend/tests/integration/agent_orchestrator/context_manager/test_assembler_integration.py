"""Integration tests for AssemblerService.

This module contains integration tests covering:
- Token service integration
- Compressor service integration
- End-to-end assembly workflows
"""

import math
from unittest.mock import AsyncMock, Mock

import pytest

from syntara.agent_orchestrator.context_manager.assembler_service import (
    AssemblerService,
    ContextAssemblyError,
)
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import (
    RelevantDocument,
)
from syntara.agent_orchestrator.token_manager.services import TokenValidationService
from syntara.files.models import FileMetadata

# ==================== Phase 3.6: Integration Tests ====================


class TestWithinBudgetNoCompression:
    """Test assembly within budget without compression."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService with mocked dependencies."""
        token_service = Mock()
        compressor_service = AsyncMock()
        return AssemblerService(token_service, compressor_service)

    @pytest.mark.asyncio
    async def test_assembly_within_budget_no_compression(self, assembler_service: AssemblerService) -> None:
        """Test documents within budget pass without compression."""
        docs = [
            RelevantDocument(
                content="Short document",
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    filename="test1.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        result = await assembler_service.assemble(
            documents=docs,
            max_tokens=10000,
            compression_loop=3,
        )

        # Verify no compression was applied
        assert result.package_metadata["compression_applied"] is False
        assert result.package_metadata["compression_retry_count"] == 0
        assert math.isclose(result.grounding_score, 0.8)
        assert len(result.citations) == 1
        # Citation is now the FileMetadata.id UUID string
        assert result.citations[0] == str(docs[0].file_metadata.id)


class TestCompressionTrigger:
    """Test compression trigger with retry loop."""

    @pytest.mark.asyncio
    async def test_compression_triggered_with_retry_loop(
        self,
        test_user,
        test_user_low_token_config,
        context_manager_session_factory,
    ) -> None:
        """Test compression triggers when documents exceed token budget.

        This integration test verifies that when:
        1. Documents exceed the token budget (detected by TokenValidationService)
        2. Compression is triggered automatically
        3. Compression succeeds on first attempt
        Then the assembly completes with compression_applied=True and retry_count=0.
        """
        # Create documents that will exceed the low token budget
        docs = [
            RelevantDocument(
                content="This is a long document that will exceed the token budget. " * 150,
                relevancy_score=0.9,
                file_metadata=FileMetadata(
                    filename="test1.txt",
                    size_bytes=5000,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        # Create assembler with real TokenValidationService
        token_service = TokenValidationService()
        compressor_service = AsyncMock()

        # Mock compression to succeed immediately with content that fits
        compressor_service.compress = AsyncMock(return_value="Compressed content within budget")

        assembler = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        # Assemble with user_id and session - should trigger compression
        result = await assembler.assemble(
            documents=docs,
            max_tokens=100,  # Very low budget to trigger compression
            compression_loop=3,  # Allow retries
            user_id=test_user.id,
            session_factory=context_manager_session_factory,
        )

        # Verify compression was triggered and succeeded
        assert result is not None
        assert result.package_metadata["compression_applied"] is True
        assert result.package_metadata["compression_retry_count"] == 0  # Succeeded on first attempt

        # Verify compression was called once
        assert compressor_service.compress.call_count == 1

        # Verify grounding score preserved
        assert math.isclose(result.grounding_score, 0.9)


class TestSuccessfulRetry:
    """Test successful retry after first compression failure."""

    @pytest.mark.asyncio
    async def test_successful_retry_after_first_failure(
        self,
        test_user,
        test_user_low_token_config,
        context_manager_session_factory,
    ) -> None:
        """Test successful compression retry after first failure.

        This integration test verifies that when:
        1. Documents exceed the token budget
        2. First compression attempt fails
        3. Second compression attempt succeeds
        Then the assembly completes successfully with retry_count=1.
        """
        # Create documents that will exceed the low token budget
        docs = [
            RelevantDocument(
                content="This is a very long document that will definitely exceed the token budget. " * 200,
                relevancy_score=0.85,
                file_metadata=FileMetadata(
                    filename="test1.txt",
                    size_bytes=10000,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        # Create assembler with real TokenValidationService
        token_service = TokenValidationService()
        compressor_service = AsyncMock()

        # Mock compression to fail once, then succeed
        compressor_service.compress = AsyncMock(
            side_effect=[
                Exception("First compression attempt failed"),  # First attempt fails
                "Compressed content that fits within budget",  # Second attempt succeeds
            ]
        )

        assembler = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        # Assemble with user_id and session - should succeed on second retry
        result = await assembler.assemble(
            documents=docs,
            max_tokens=100,  # Very low budget to trigger compression
            compression_loop=3,  # Allow up to 3 retries
            user_id=test_user.id,
            session_factory=context_manager_session_factory,
        )

        # Verify assembly succeeded
        assert result is not None
        assert result.package_metadata["compression_applied"] is True
        assert result.package_metadata["compression_retry_count"] == 1  # Succeeded on second attempt (retry 1)

        # Verify compression was called twice (failed once, succeeded once)
        assert compressor_service.compress.call_count == 2


class TestMultipleRetries:
    """Test multiple compression retry attempts."""

    @pytest.mark.asyncio
    async def test_multiple_compression_retries(
        self,
        test_user,
        test_user_low_token_config,
        context_manager_session_factory,
    ) -> None:
        """Test multiple compression retries with progressive strategies.

        This integration test verifies that when:
        1. Documents exceed the token budget
        2. First and second compression attempts fail
        3. Third compression attempt succeeds
        Then the assembly completes successfully with retry_count=2.
        """
        # Create documents that will exceed the low token budget
        docs = [
            RelevantDocument(
                content="This is a very long document that will definitely exceed the token budget. " * 200,
                relevancy_score=0.75,
                file_metadata=FileMetadata(
                    filename="test1.txt",
                    size_bytes=10000,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        # Create assembler with real TokenValidationService
        token_service = TokenValidationService()
        compressor_service = AsyncMock()

        # Mock compression to fail twice, then succeed on third attempt
        compressor_service.compress = AsyncMock(
            side_effect=[
                Exception("First compression attempt failed"),  # Retry 0 fails
                Exception("Second compression attempt failed"),  # Retry 1 fails
                "Compressed content that fits within budget",  # Retry 2 succeeds
            ]
        )

        assembler = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        # Assemble with user_id and session - should succeed on third attempt
        result = await assembler.assemble(
            documents=docs,
            max_tokens=100,  # Very low budget to trigger compression
            compression_loop=3,  # Allow up to 3 retries
            user_id=test_user.id,
            session_factory=context_manager_session_factory,
        )

        # Verify assembly succeeded
        assert result is not None
        assert result.package_metadata["compression_applied"] is True
        assert result.package_metadata["compression_retry_count"] == 2  # Succeeded on third attempt (retry 2)

        # Verify compression was called 3 times (failed twice, succeeded once)
        assert compressor_service.compress.call_count == 3


class TestExhaustedRetriesRejection:
    """Test exhausted retries raise error."""

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_raises_error(
        self,
        test_user,
        test_user_low_token_config,
        context_manager_session_factory,
    ) -> None:
        """Test ContextAssemblyError raised when all compression retries exhausted.

        This integration test verifies that when:
        1. Documents exceed the token budget
        2. Compression is triggered via TokenValidationService
        3. All compression retry attempts fail
        Then a ContextAssemblyError is raised with the correct retry_count.
        """
        # Create documents that will exceed the low token budget
        docs = [
            RelevantDocument(
                content="This is a very long document that will definitely exceed the token budget. " * 200,
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    filename="test1.txt",
                    size_bytes=10000,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        # Create assembler with real TokenValidationService and mock compressor that always fails
        token_service = TokenValidationService()
        compressor_service = AsyncMock()
        # Mock compression to always fail on every retry
        compressor_service.compress = AsyncMock(side_effect=Exception("Compression failed"))

        assembler = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        # Assemble with user_id and session - should trigger compression and exhaust retries
        with pytest.raises(ContextAssemblyError) as exc_info:
            await assembler.assemble(
                documents=docs,
                max_tokens=100,  # Very low budget to trigger compression
                compression_loop=3,  # 3 retry attempts
                user_id=test_user.id,
                session_factory=context_manager_session_factory,
            )

        # Verify error details
        error = exc_info.value
        assert error.retry_count == 3
        assert "Content exceeds token limit" in str(error)
        assert "after 3 compression retries" in str(error)

        # Verify compression was attempted 3 times
        assert compressor_service.compress.call_count == 3


class TestCompressionLoopZeroFailure:
    """Test compression_loop=0 immediate failure."""

    @pytest.mark.asyncio
    async def test_compression_loop_zero_immediate_failure(
        self,
        test_user,
        test_user_low_token_config,
        context_manager_session_factory,
    ) -> None:
        """Test immediate failure with compression_loop=0 when documents exceed budget.

        This integration test verifies that when:
        1. Documents exceed the token budget
        2. compression_loop=0 (no retries allowed)
        3. TokenValidationService detects the limit exceeded
        Then a ContextAssemblyError is raised immediately with retry_count=0.
        """
        # Create documents that will exceed the low token budget
        docs = [
            RelevantDocument(
                content="This is a very long document that will definitely exceed the token budget. " * 200,
                relevancy_score=0.9,
                file_metadata=FileMetadata(
                    filename="test1.txt",
                    size_bytes=10000,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        # Create assembler with real TokenValidationService
        # Compressor should NOT be called since compression_loop=0
        token_service = TokenValidationService()
        compressor_service = AsyncMock()

        assembler = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        # Assemble with compression_loop=0 - should fail immediately when budget exceeded
        with pytest.raises(ContextAssemblyError) as exc_info:
            await assembler.assemble(
                documents=docs,
                max_tokens=100,  # Very low budget to trigger failure
                compression_loop=0,  # No retries allowed
                user_id=test_user.id,
                session_factory=context_manager_session_factory,
            )

        # Verify error details
        error = exc_info.value
        assert error.retry_count == 0  # No retries with compression_loop=0
        # Error message should indicate retries were exhausted with 0 attempts
        assert "Compression retries exhausted" in str(error) or "0 attempts" in str(error)

        # Verify compressor was NEVER called (no retries)
        compressor_service.compress.assert_not_called()


class TestEndToEndWithCitations:
    """Test end-to-end assembly with citation extraction."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService with mocked dependencies."""
        token_service = Mock()
        compressor_service = AsyncMock()
        return AssemblerService(token_service, compressor_service)

    @pytest.mark.asyncio
    async def test_end_to_end_assembly_with_citations(self, assembler_service: AssemblerService) -> None:
        """Test full workflow with citation extraction from FileMetadata.id."""
        docs = [
            RelevantDocument(
                content="Document 1",
                relevancy_score=0.7,
                file_metadata=FileMetadata(
                    filename="test1.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
            RelevantDocument(
                content="Document 2",
                relevancy_score=0.9,
                file_metadata=FileMetadata(
                    filename="test2.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/file2.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        result = await assembler_service.assemble(
            documents=docs,
            max_tokens=10000,
            compression_loop=0,
        )

        # Verify citations from FileMetadata.id UUIDs
        assert len(result.citations) == 2
        assert str(docs[0].file_metadata.id) in result.citations
        assert str(docs[1].file_metadata.id) in result.citations

        # Verify grounding score computed correctly
        expected_score = (0.7 + 0.9) / 2
        assert math.isclose(result.grounding_score, expected_score)

        # Verify document content assembled
        assert result.payload is not None
        assert "documents" in result.payload
        assert len(result.payload["documents"]) == 2
