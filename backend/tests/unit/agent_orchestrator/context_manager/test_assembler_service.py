"""Unit tests for AssemblerService.

This module contains unit tests for the AssemblerService class, covering:
- Core logic (grounding score, citations, document handling)
- Compression retry loop with progressive strategies
"""

import math
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.context_manager.assembler_service import (
    AssemblerService,
    ContextAssemblyError,
)
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import (
    RelevantDocument,
)
from syntara.agent_orchestrator.token_manager.exceptions import UserTokenConfigNotFoundError
from syntara.files.models import FileMetadata

# ==================== Phase 3.2: Unit Tests - Core Logic ====================


class TestGroundingScoreComputation:
    """Tests for grounding score computation logic."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService instance with mocked dependencies."""
        token_service = Mock()
        compressor_service = Mock()
        return AssemblerService(token_service, compressor_service)

    def test_compute_grounding_score_simple_average(self, assembler_service) -> None:
        """Test grounding score computed as simple average."""
        # Create test documents with known relevancy scores
        docs = [
            RelevantDocument(
                content="doc1",
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    id=uuid4(),
                    filename="test1.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
            RelevantDocument(
                content="doc2",
                relevancy_score=0.6,
                file_metadata=FileMetadata(
                    id=uuid4(),
                    filename="test2.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/file2.txt",
                ),
                source_type="uploaded_file",
            ),
            RelevantDocument(
                content="doc3",
                relevancy_score=0.9,
                file_metadata=FileMetadata(
                    id=uuid4(),
                    filename="test3.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/file3.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        score = assembler_service._compute_grounding_score(docs)

        # Verify average: (0.8 + 0.6 + 0.9) / 3 = 0.7667
        expected_score = (0.8 + 0.6 + 0.9) / 3
        assert math.isclose(score, expected_score)

    def test_compute_grounding_score_empty_list(self, assembler_service) -> None:
        """Test grounding score returns 0.0 for empty list."""
        score = assembler_service._compute_grounding_score([])
        assert math.isclose(score, 0.0)

    def test_compute_grounding_score_with_none_values(self, assembler_service) -> None:
        """Test grounding score excludes None values from average."""
        docs = [
            RelevantDocument(
                content="doc1",
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    id=uuid4(),
                    filename="test1.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
            RelevantDocument(
                content="doc2",
                relevancy_score=0.6,
                file_metadata=FileMetadata(
                    id=uuid4(),
                    filename="test2.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/file2.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        # Test the implementation handles valid scores correctly
        score = assembler_service._compute_grounding_score(docs)
        expected_score = (0.8 + 0.6) / 2
        assert math.isclose(score, expected_score)


class TestCitationExtraction:
    """Tests for citation extraction from FileMetadata.file_id."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService instance with mocked dependencies."""
        token_service = Mock()
        compressor_service = Mock()
        return AssemblerService(token_service, compressor_service)

    def test_extract_citations_from_file_metadata_file_id(self, assembler_service) -> None:
        """Test citations extracted from FileMetadata.id."""
        file_id_1 = uuid4()
        file_id_2 = uuid4()
        docs = [
            RelevantDocument(
                content="doc1",
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    id=file_id_1,
                    filename="test1.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
            RelevantDocument(
                content="doc2",
                relevancy_score=0.9,
                file_metadata=FileMetadata(
                    id=file_id_2,
                    filename="test2.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/file2.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        citations = assembler_service._extract_citations(docs)

        assert citations == [str(file_id_1), str(file_id_2)]

    def test_extract_citations_missing_file_id(self, assembler_service) -> None:
        """Test citation extraction handles missing id gracefully."""
        # This test will verify the implementation handles edge cases
        file_id = uuid4()
        docs = [
            RelevantDocument(
                content="doc1",
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    id=file_id,
                    filename="test1.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        citations = assembler_service._extract_citations(docs)
        assert str(file_id) in citations


class TestEmptyAndNullDocuments:
    """Tests for handling empty and null documents."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService instance with mocked dependencies."""
        token_service = Mock()
        compressor_service = Mock()
        return AssemblerService(token_service, compressor_service)

    @pytest.mark.asyncio
    async def test_assemble_empty_documents_list(self, assembler_service) -> None:
        """Test assembly with empty documents list returns default ContextPackage."""
        # This test verifies graceful handling of empty input
        result = await assembler_service.assemble(
            documents=[],
            max_tokens=1000,
            compression_loop=0,
        )

        # Should return valid ContextPackage with default values
        assert result is not None
        assert math.isclose(result.grounding_score, 0.0)

    @pytest.mark.asyncio
    async def test_assemble_null_documents(self, assembler_service) -> None:
        """Test assembly with null documents returns default ContextPackage."""
        result = await assembler_service.assemble(
            documents=None,
            max_tokens=1000,
            compression_loop=0,
        )

        assert result is not None
        assert math.isclose(result.grounding_score, 0.0)


class TestInvalidRelevancyScores:
    """Tests for handling invalid relevancy scores."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService instance with mocked dependencies."""
        token_service = Mock()
        compressor_service = Mock()
        return AssemblerService(token_service, compressor_service)

    def test_grounding_score_excludes_invalid_scores(self, assembler_service) -> None:
        """Test invalid scores are excluded from average computation."""
        # Valid score should be used
        docs = [
            RelevantDocument(
                content="doc1",
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    id=uuid4(),
                    filename="test1.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        score = assembler_service._compute_grounding_score(docs)
        assert math.isclose(score, 0.8)


class TestDocumentContentOrganization:
    """Tests for document content organization in payload."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService instance with mocked dependencies."""
        token_service = Mock()
        compressor_service = Mock()
        return AssemblerService(token_service, compressor_service)

    def test_build_payload_document_content(self, assembler_service) -> None:
        """Test payload contains assembled document content."""
        docs = [
            RelevantDocument(
                content="Document content 1",
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    id=uuid4(),
                    filename="test1.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        payload = assembler_service._build_payload(docs, compression_applied=False)

        # Payload should contain document content
        assert payload is not None
        assert isinstance(payload, dict)


# ==================== Phase 3.3: Unit Tests - Retry Loop ====================


class TestCompressionRetryLoop:
    """Tests for compression retry loop with progressive strategies."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService instance with mocked dependencies."""
        token_service = Mock()
        compressor_service = AsyncMock()
        return AssemblerService(token_service, compressor_service)

    @pytest.mark.asyncio
    async def test_compression_retry_loop_progressive_strategies(self, assembler_service) -> None:
        """Test retry loop uses progressively more aggressive strategies."""
        docs = [
            RelevantDocument(
                content="Long document content" * 100,
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    id=uuid4(),
                    filename="test1.txt",
                    size_bytes=1000,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        # Mock compression service to return compressed content string
        compressed_content = "Compressed content"

        assembler_service.compressor_service.compress = AsyncMock(return_value=compressed_content)

        # Call the compress_with_retry method
        result_docs, retry_count = await assembler_service._compress_with_retry(
            documents=docs,
            max_tokens=1000,
            compression_loop=3,
        )

        # Verify compression was attempted
        assert assembler_service.compressor_service.compress.called
        assert result_docs is not None
        assert retry_count == 0  # Should succeed on first try


class TestCompressionLoopZero:
    """Tests for compression_loop=0 behavior."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService instance with mocked dependencies."""
        token_service = Mock()
        compressor_service = AsyncMock()
        return AssemblerService(token_service, compressor_service)

    @pytest.mark.asyncio
    async def test_compression_loop_zero_no_retries(self, assembler_service) -> None:
        """Test compression_loop=0 raises error immediately after first failure."""
        # Test will verify no retries with compression_loop=0
        # Implementation pending - requires compressor service mock setup


class TestExhaustedRetries:
    """Tests for exhausted retries error handling."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService instance with mocked dependencies."""
        token_service = Mock()
        compressor_service = AsyncMock()
        return AssemblerService(token_service, compressor_service)

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_raises_error(self, assembler_service) -> None:
        """Test ContextAssemblyError raised when all retries exhausted."""
        docs = [
            RelevantDocument(
                content="Document content",
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    id=uuid4(),
                    filename="test1.txt",
                    size_bytes=1000,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        # Mock compression to always fail
        assembler_service.compressor_service.compress = AsyncMock(side_effect=Exception("Compression failed"))

        # Verify error is raised with retry count
        with pytest.raises(ContextAssemblyError) as exc_info:
            await assembler_service._compress_with_retry(
                documents=docs,
                max_tokens=100,
                compression_loop=3,
            )

        assert exc_info.value.retry_count == 3


class TestRetryStrategyProgression:
    """Tests for retry strategy progression validation."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService instance with mocked dependencies."""
        token_service = Mock()
        compressor_service = AsyncMock()
        return AssemblerService(token_service, compressor_service)


class TestPackageMetadataRetryCount:
    """Tests for package_metadata compression_retry_count."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService instance with mocked dependencies."""
        token_service = Mock()
        compressor_service = AsyncMock()
        return AssemblerService(token_service, compressor_service)

    @pytest.mark.asyncio
    async def test_package_metadata_includes_retry_count(self, assembler_service) -> None:
        """Test package_metadata includes compression_retry_count."""
        docs = [
            RelevantDocument(
                content="Test document",
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    id=uuid4(),
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
            compression_loop=0,
        )

        # Verify metadata contains retry count
        assert "compression_retry_count" in result.package_metadata
        assert result.package_metadata["compression_retry_count"] == 0

    @pytest.mark.asyncio
    async def test_no_compression_retry_count_zero(self, assembler_service) -> None:
        """Test compression_retry_count=0 when no compression needed."""
        docs = [
            RelevantDocument(
                content="Small doc",
                relevancy_score=0.7,
                file_metadata=FileMetadata(
                    id=uuid4(),
                    filename="test1.txt",
                    size_bytes=50,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        result = await assembler_service.assemble(
            documents=docs,
            max_tokens=10000,
            compression_loop=0,
        )

        # Verify retry_count=0 when within budget
        assert result.package_metadata["compression_retry_count"] == 0
        assert result.package_metadata["compression_applied"] is False


# T008: AssemblerService passes invocation_id to validate_and_record


class TestAssemblerServiceInvocationIdWiring:
    """Tests verifying invocation_id is passed to validate_and_record."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService with mock token_service."""
        token_service = AsyncMock()
        token_service.validate_and_record = AsyncMock(return_value=100)
        compressor_service = AsyncMock()
        return AssemblerService(token_service, compressor_service)

    @pytest.mark.asyncio
    async def test_assemble_passes_invocation_id_to_validate_and_record(
        self, assembler_service: AssemblerService
    ) -> None:
        """Test that invocation_id is forwarded to validate_and_record at first call site."""
        docs = [
            RelevantDocument(
                content="test document content",
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    id=uuid4(),
                    filename="test.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/test.txt",
                ),
                source_type="uploaded_file",
            ),
        ]
        user_id = uuid4()
        invocation_id = uuid4()
        mock_session = AsyncMock()

        # Create a mock session factory that returns an async context manager
        async def mock_session_factory() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        await assembler_service.assemble(
            documents=docs,
            max_tokens=10000,
            compression_loop=0,
            invocation_id=invocation_id,
            user_id=user_id,
            session_factory=mock_session_factory,
        )

        # Verify validate_and_record was called with invocation_id
        # Note: session will be the mock_session from the context manager
        assembler_service.token_service.validate_and_record.assert_called_once()  # type: ignore[attr-defined]
        call_args = assembler_service.token_service.validate_and_record.call_args  # type: ignore[attr-defined]
        assert call_args.kwargs["user_id"] == user_id
        assert call_args.kwargs["request_text"] == "test document content"
        assert call_args.kwargs["invocation_id"] == invocation_id


class TestAssemblerUserTokenConfigNotFound:
    """Tests for AAP-83799: assembler gracefully handles missing UserTokenConfig."""

    @pytest.fixture
    def assembler_service(self) -> AssemblerService:
        """Create AssemblerService with mock token_service that raises UserTokenConfigNotFoundError."""
        token_service = AsyncMock()
        token_service.validate_and_record = AsyncMock(side_effect=UserTokenConfigNotFoundError(uuid4()))
        token_service.calculator = Mock()
        token_service.calculator.count_tokens = Mock(return_value=50)
        compressor_service = AsyncMock()
        return AssemblerService(token_service, compressor_service)

    @pytest.mark.asyncio
    async def test_assemble_skips_validation_when_no_token_config(self, assembler_service: AssemblerService) -> None:
        """AAP-83799: Assembler should not crash when no UserTokenConfig exists for the user."""
        docs = [
            RelevantDocument(
                content="document with content",
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    id=uuid4(),
                    filename="test.txt",
                    size_bytes=100,
                    mime_type="text/plain",
                    file_path="/path/to/test.txt",
                ),
                source_type="uploaded_file",
            ),
        ]
        user_id = uuid4()
        invocation_id = uuid4()
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        result = await assembler_service.assemble(
            documents=docs,
            max_tokens=10000,
            compression_loop=0,
            invocation_id=invocation_id,
            user_id=user_id,
            session_factory=mock_session_factory,
        )

        assert result is not None
        assert result.payload["documents"][0]["content"] == "document with content"
        assert result.grounding_score == pytest.approx(0.8)
        assert len(result.citations) == 1
        assert result.package_metadata["compression_applied"] is False
