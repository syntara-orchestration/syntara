"""Integration tests for AssemblerService with TokenValidationService.

This module contains integration tests for the full token validation workflow,
including database interactions and real token counting.
"""

import math
from unittest.mock import AsyncMock

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


@pytest.mark.asyncio
class TestTokenValidationIntegration:
    """Integration tests for token validation with AssemblerService."""

    @pytest.mark.usefixtures("test_user_token_config")
    async def test_within_budget_no_compression_with_real_token_service(
        self,
        context_manager_session_factory,
        test_user,
    ) -> None:
        """Test documents within budget using real TokenValidationService."""
        # Create short documents that will be within token budget
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

        # Create assembler with real TokenValidationService
        token_service = TokenValidationService()
        compressor_service = AsyncMock()
        assembler = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        # Assemble with user_id and session
        result = await assembler.assemble(
            documents=docs,
            max_tokens=10000,  # Large budget
            compression_loop=3,
            user_id=test_user.id,
            session_factory=context_manager_session_factory,
        )

        # Verify no compression was applied
        assert result.package_metadata["compression_applied"] is False
        assert result.package_metadata["compression_retry_count"] == 0
        assert result.package_metadata["original_token_count"] > 0
        assert result.package_metadata["final_token_count"] > 0
        assert math.isclose(result.grounding_score, 0.8)

        # Verify compressor was NOT called
        compressor_service.compress.assert_not_called()

    @pytest.mark.usefixtures("test_user_low_token_config")
    async def test_token_limit_exceeded_triggers_compression(
        self,
        context_manager_session_factory,
        test_user,
    ) -> None:
        """Test token limit exceeded triggers compression retry loop."""
        # Create documents that will exceed a low token budget
        docs = [
            RelevantDocument(
                content="This is a longer document that will exceed the token budget. " * 100,
                relevancy_score=0.9,
                file_metadata=FileMetadata(
                    filename="test1.txt",
                    size_bytes=1000,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        # Create compressed content string
        compressed_content = "Compressed version"

        # Create assembler with mocked compressor
        token_service = TokenValidationService()
        compressor_service = AsyncMock()
        compressor_service.compress = AsyncMock(return_value=compressed_content)

        assembler = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        # Assemble - should trigger compression
        result = await assembler.assemble(
            documents=docs,
            max_tokens=10000,
            compression_loop=3,
            user_id=test_user.id,
            session_factory=context_manager_session_factory,
        )

        # Verify compression was applied
        assert result.package_metadata["compression_applied"] is True
        assert result.package_metadata["original_token_count"] > 0

        # Verify compressor WAS called
        assert compressor_service.compress.called

    @pytest.mark.usefixtures("test_user_low_token_config")
    async def test_compression_retry_with_progressive_strategies(
        self,
        context_manager_session_factory,
        test_user,
    ) -> None:
        """Test compression retry uses progressively more aggressive strategies."""
        # Create large documents
        docs = [
            RelevantDocument(
                content="Large document content " * 200,
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    filename="test1.txt",
                    size_bytes=2000,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        # First compression still too large, second succeeds
        failed_compression_content = "Still too large " * 100
        successful_compression_content = "Small compressed"

        token_service = TokenValidationService()
        compressor_service = AsyncMock()
        # First call returns still-large content, second returns small
        compressor_service.compress = AsyncMock(
            side_effect=[failed_compression_content, successful_compression_content]
        )

        assembler = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        result = await assembler.assemble(
            documents=docs,
            max_tokens=10000,
            compression_loop=3,
            user_id=test_user.id,
            session_factory=context_manager_session_factory,
        )

        # Verify compression was applied with retries
        assert result.package_metadata["compression_applied"] is True
        # Should have tried compression at least twice (first fails, second succeeds)
        assert compressor_service.compress.call_count >= 2

        # Verify compress was called with expected arguments
        # All calls should have the same structure
        for call in compressor_service.compress.call_args_list:
            _, kwargs = call
            # Should be called with keyword arguments
            assert "data" in kwargs
            assert "max_tokens" in kwargs
            assert "strategy" in kwargs
            # Verify argument values
            assert isinstance(kwargs["data"], list)
            assert all(isinstance(item, str) for item in kwargs["data"])
            assert kwargs["max_tokens"] == 10000
            assert kwargs["strategy"] == "greedy"

    @pytest.mark.usefixtures("test_user_low_token_config")
    async def test_all_retries_exhausted_raises_context_assembly_error(
        self,
        context_manager_session_factory,
        test_user,
    ) -> None:
        """Test ContextAssemblyError when all compression retries exhausted."""
        # Create documents that cannot be compressed enough
        docs = [
            RelevantDocument(
                content="Very large document " * 1000,
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

        # Compression always returns still-too-large content string
        still_too_large_content = "Still too large " * 500

        token_service = TokenValidationService()
        compressor_service = AsyncMock()
        compressor_service.compress = AsyncMock(return_value=still_too_large_content)

        assembler = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        # Should raise ContextAssemblyError after exhausting retries
        with pytest.raises(ContextAssemblyError) as exc_info:
            await assembler.assemble(
                documents=docs,
                max_tokens=10000,
                compression_loop=2,  # Allow 2 retries
                user_id=test_user.id,
                session_factory=context_manager_session_factory,
            )

        # Verify error details
        assert exc_info.value.retry_count == 2

    @pytest.mark.usefixtures("test_user_token_config")
    async def test_token_usage_recorded_in_database(
        self,
        test_db_session_factory,
        context_manager_session_factory,
        test_user,
    ) -> None:
        """Test token usage is properly recorded in database."""
        docs = [
            RelevantDocument(
                content="Test document",
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

        token_service = TokenValidationService()
        compressor_service = AsyncMock()
        assembler = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        # Get usage before - need fresh session to see committed data
        async with test_db_session_factory() as session:
            usage_before = await token_service.get_current_usage(
                user_id=test_user.id,
                session=session,
            )

        # Assemble documents
        await assembler.assemble(
            documents=docs,
            max_tokens=10000,
            compression_loop=3,
            user_id=test_user.id,
            session_factory=context_manager_session_factory,
        )

        # Get usage after - need fresh session to see committed data
        async with test_db_session_factory() as session:
            usage_after = await token_service.get_current_usage(
                user_id=test_user.id,
                session=session,
            )

        # Verify token usage was recorded
        assert usage_after["current_usage"] > usage_before["current_usage"]
