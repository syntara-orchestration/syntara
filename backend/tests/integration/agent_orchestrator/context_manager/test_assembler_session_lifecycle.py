"""Integration tests for AssemblerService session lifecycle.

This module verifies that DB sessions are short-lived and released before
long-running operations like LLM compression calls (AAP-77243).
"""

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.context_manager.assembler_service import AssemblerService
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import (
    RelevantDocument,
)
from syntara.agent_orchestrator.token_manager.services import TokenValidationService
from syntara.files.models import FileMetadata


class SessionLifecycleTracker:
    """Track session open/close events to verify proper lifecycle management."""

    def __init__(self) -> None:
        """Initialize the tracker."""
        self.sessions_opened = 0
        self.sessions_closed = 0
        self.sessions_active_during_compression = 0
        self.compression_started = False
        self.compression_completed = False

    @asynccontextmanager
    async def tracked_session_factory(
        self, original_factory: Callable[[], AsyncGenerator[AsyncSession, None]]
    ) -> AsyncGenerator[AsyncSession, None]:
        """Wrap session factory to track lifecycle events."""
        self.sessions_opened += 1

        # original_factory returns an AsyncGenerator, wrap it as async context manager
        async with asynccontextmanager(original_factory)() as session:
            try:
                yield session
            finally:
                # Check if session is being held during compression
                if self.compression_started and not self.compression_completed:
                    self.sessions_active_during_compression += 1
                self.sessions_closed += 1

    def mark_compression_start(self) -> None:
        """Mark the start of compression (long-running LLM call)."""
        self.compression_started = True

    def mark_compression_complete(self) -> None:
        """Mark the completion of compression."""
        self.compression_completed = True


@pytest.mark.asyncio
class TestSessionLifecycle:
    """Tests for session lifecycle management in AssemblerService."""

    @pytest.mark.usefixtures("test_user_low_token_config")
    async def test_session_released_before_compression(
        self,
        test_db_session,
        test_db_session_factory,
        test_user,
    ) -> None:
        """Test that DB sessions are released before compression starts.

        This test verifies the fix for AAP-77243: DB connections should NOT
        be held during long-running LLM compression calls.

        Expected behavior:
        1. Open session for pre-compression token validation
        2. Close session
        3. Run compression (NO active DB session)
        4. Open new session for post-compression validation
        5. Close session

        This ensures minimal connection holding time (~100ms per validation)
        instead of holding for the entire compression duration (10-60 seconds).
        """
        # Create documents that will trigger compression
        docs = [
            RelevantDocument(
                content="This is a longer document that will exceed the token budget. " * 100,
                relevancy_score=0.9,
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

        # Create lifecycle tracker
        tracker = SessionLifecycleTracker()

        # Create a session factory from the test database session factory
        async def test_session_gen() -> AsyncGenerator[AsyncSession, None]:
            """Wrap the session factory to match expected signature."""
            async with test_db_session_factory() as session:
                yield session

        # Create session factory that tracks lifecycle
        async def tracked_session_factory() -> AsyncGenerator[AsyncSession, None]:
            async with tracker.tracked_session_factory(test_session_gen) as session:
                yield session

        # Create compressor that simulates long-running LLM call
        compressor_service = AsyncMock()

        async def mock_compress(*args: object, **kwargs: object) -> str:
            """Mock compression that tracks when it runs."""
            tracker.mark_compression_start()
            # Simulate LLM call duration
            await asyncio.sleep(0.1)  # 100ms to simulate network call
            tracker.mark_compression_complete()
            return "Compressed content"

        compressor_service.compress = AsyncMock(side_effect=mock_compress)

        # Create assembler with real TokenValidationService
        token_service = TokenValidationService()
        assembler = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        # Assemble with tracked session factory
        result = await assembler.assemble(
            documents=docs,
            max_tokens=10000,
            compression_loop=3,
            user_id=test_user.id,
            session_factory=tracked_session_factory,
        )

        # Verify compression was triggered
        assert result.package_metadata["compression_applied"] is True
        assert compressor_service.compress.called

        # CRITICAL ASSERTION: No sessions should be active during compression
        # This is the fix for AAP-77243 - sessions must be released before compression
        assert tracker.sessions_active_during_compression == 0, (
            f"Expected 0 active sessions during compression, but found {tracker.sessions_active_during_compression}"
        )

        # Verify sessions were opened and closed properly
        assert tracker.sessions_opened > 0, "At least one session should have been opened"
        assert tracker.sessions_opened == tracker.sessions_closed, "All opened sessions should be closed"

    @pytest.mark.usefixtures("test_user_low_token_config")
    async def test_multiple_retries_use_separate_sessions(
        self,
        test_db_session,
        test_db_session_factory,
        test_user,
    ) -> None:
        """Test that each compression retry uses its own short-lived session.

        When compression retries, each attempt should:
        1. Open session for token validation
        2. Close session
        3. Run compression
        4. Open new session for validation
        5. Close session

        This ensures connection pool is not exhausted during retry loops.
        """
        # Create documents that will trigger multiple compression retries
        docs = [
            RelevantDocument(
                content="Large document content " * 200,
                relevancy_score=0.8,
                file_metadata=FileMetadata(
                    id=uuid4(),
                    filename="test1.txt",
                    size_bytes=2000,
                    mime_type="text/plain",
                    file_path="/path/to/file1.txt",
                ),
                source_type="uploaded_file",
            ),
        ]

        # Create lifecycle tracker
        tracker = SessionLifecycleTracker()

        # Create a session factory from the test database session factory
        async def test_session_gen() -> AsyncGenerator[AsyncSession, None]:
            """Wrap the session factory to match expected signature."""
            async with test_db_session_factory() as session:
                yield session

        # Create session factory that tracks lifecycle
        async def tracked_session_factory() -> AsyncGenerator[AsyncSession, None]:
            async with tracker.tracked_session_factory(test_session_gen) as session:
                yield session

        # First compression returns still-large content, second succeeds
        failed_compression = "Still too large " * 100
        successful_compression = "Small compressed"

        compressor_service = AsyncMock()
        compression_call_count = 0

        async def mock_compress(*args: object, **kwargs: object) -> str:
            """Mock compression with retry logic."""
            nonlocal compression_call_count
            compression_call_count += 1

            tracker.mark_compression_start()
            await asyncio.sleep(0.1)  # Simulate LLM call

            result = failed_compression if compression_call_count == 1 else successful_compression
            tracker.mark_compression_complete()
            tracker.compression_started = False  # Reset for next retry
            tracker.compression_completed = False  # Reset for next retry
            return result

        compressor_service.compress = AsyncMock(side_effect=mock_compress)

        # Create assembler
        token_service = TokenValidationService()
        assembler = AssemblerService(
            token_service=token_service,
            compressor_service=compressor_service,
        )

        # Assemble with retries
        result = await assembler.assemble(
            documents=docs,
            max_tokens=10000,
            compression_loop=3,
            user_id=test_user.id,
            session_factory=tracked_session_factory,
        )

        # Verify compression retries occurred
        assert result.package_metadata["compression_applied"] is True
        assert compressor_service.compress.call_count >= 2

        # CRITICAL: No sessions held during ANY compression attempt
        assert tracker.sessions_active_during_compression == 0

        # Verify multiple sessions were used (one per validation)
        # Expect at least: pre-compression validation + (N retries x post-compression validation)
        assert tracker.sessions_opened >= 2
        assert tracker.sessions_opened == tracker.sessions_closed
