"""Integration tests for ContextManagerPlanner with AssemblerService.

This module tests the planner integration with the real AssemblerService,
verifying proper dependency injection and parameter passing.
"""

import math
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractContextManager
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.context_manager.models import ContextPackage
from syntara.agent_orchestrator.context_manager.planner import ContextManagerPlanner
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import (
    RelevantDocument,
)
from syntara.agent_orchestrator.context_manager.retriever_service.services import RetrieverService
from syntara.agent_orchestrator.models import Invocation
from syntara.core.models import User
from syntara.files.models import FileMetadata
from tests.fixtures.settings import FakeSettingsCache


@pytest.fixture(autouse=True)
def _mock_runtime_settings(override_runtime_settings: Callable[..., AbstractContextManager[FakeSettingsCache]]) -> None:  # type: ignore[misc]
    """Auto-mock get_runtime_settings for all planner integration tests."""
    with override_runtime_settings():
        yield


def create_test_document(
    content: str,
    relevancy_score: float,
    filename: str = "test1.txt",
) -> RelevantDocument:
    """Create a test RelevantDocument with common defaults."""
    return RelevantDocument(
        content=content,
        relevancy_score=relevancy_score,
        file_metadata=FileMetadata(
            filename=filename,
            size_bytes=100,
            mime_type="text/plain",
            file_path=f"/path/to/{filename}",
            project_id=uuid4(),
        ),
        source_type="uploaded_file",
    )


def create_mock_retriever(docs: list[RelevantDocument]) -> AsyncMock:
    """Create a mocked RetrieverService that returns the given documents."""
    mock_retriever = AsyncMock()
    mock_retriever.retrieve_relevant_documents.return_value = docs
    return mock_retriever


def create_retriever_factory(
    mock_retriever: AsyncMock,
) -> Callable[[Callable[[], AsyncGenerator[AsyncSession, None]]], RetrieverService]:
    """Create a retriever factory that returns the mocked retriever."""

    def factory(session_factory: Callable[[], AsyncGenerator[AsyncSession, None]]) -> AsyncMock:
        return mock_retriever

    return factory


async def execute_planner_request(
    planner: ContextManagerPlanner,
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> ContextPackage:
    """Execute plan_request with standard setup.

    This helper reduces duplication by encapsulating the common pattern of:
    - Creating invocation in test DB
    - Executing plan_request with user_id
    """
    invocation = Invocation(
        created_by=test_user.id, prompt="test", session_id="session-abc", project_id=test_project_id
    )
    test_db_session.add(invocation)
    await test_db_session.commit()  # Commit so other sessions can see the invocation
    await test_db_session.refresh(invocation)
    invocation_id = invocation.id

    return await planner.plan_request(
        query="test query",
        session_id="test-session",
        invocation_id=invocation_id,
        execution_id=uuid4(),
        request_id=uuid4(),
        user_id=test_user.id,
    )


@pytest.mark.asyncio
class TestPlannerAssemblerIntegration:
    """Integration tests for planner with AssemblerService."""

    @pytest.mark.usefixtures("test_user_token_config")
    async def test_planner_invokes_assembler_with_compression_loop(
        self,
        test_db_session,
        test_user,
        mock_compressor,
        context_manager_session_factory,
        test_project_id,
    ) -> None:
        """Test planner passes compression_loop parameter correctly to AssemblerService."""
        docs = [create_test_document("Test document content", 0.8)]

        mock_retriever = create_mock_retriever(docs)

        planner = ContextManagerPlanner(
            retriever_service_factory=create_retriever_factory(mock_retriever),
            compressor_service_factory=lambda: mock_compressor,
            session_factory=context_manager_session_factory,
        )

        result = await execute_planner_request(planner, test_db_session, test_user, test_project_id)

        # Verify ContextPackage was returned
        assert result is not None
        # Verify package_metadata contains compression info
        assert "compression_applied" in result.package_metadata
        assert "compression_retry_count" in result.package_metadata

        # Verify retriever was called
        mock_retriever.retrieve_relevant_documents.assert_called_once()

    @pytest.mark.usefixtures("test_user_token_config")
    async def test_planner_injects_dependencies_into_assembler(
        self,
        test_db_session,
        test_user,
        mock_compressor,
        context_manager_session_factory,
        test_project_id,
    ) -> None:
        """Test planner injects TokenValidationService and CompressorService into AssemblerService."""
        doc = create_test_document("Short document", 0.9)
        docs = [doc]

        mock_retriever = create_mock_retriever(docs)

        planner = ContextManagerPlanner(
            retriever_service_factory=create_retriever_factory(mock_retriever),
            compressor_service_factory=lambda: mock_compressor,
            session_factory=context_manager_session_factory,
        )

        result = await execute_planner_request(planner, test_db_session, test_user, test_project_id)

        # Verify result is valid
        assert result is not None
        # Verify grounding score was computed (indicates AssemblerService worked)
        assert math.isclose(result.grounding_score, 0.9)

        # Verify citations were extracted (now use FileMetadata.id UUIDs)
        assert len(result.citations) == 1
        assert result.citations[0] == str(doc.file_metadata.id)

    @pytest.mark.usefixtures("test_user_token_config")
    async def test_planner_calls_assembler_with_injected_compressor(
        self,
        test_db_session,
        test_user,
        context_manager_session_factory,
        test_project_id,
    ) -> None:
        """Test planner injects CompressorService into AssemblerService correctly."""
        docs = [create_test_document("Test content", 0.8)]

        # Mock compressor to verify it gets injected (custom behavior for this test)
        custom_mock_compressor = AsyncMock()
        custom_mock_compressor.compress = AsyncMock(return_value="Compressed content")

        mock_retriever = create_mock_retriever(docs)

        planner = ContextManagerPlanner(
            retriever_service_factory=create_retriever_factory(mock_retriever),
            compressor_service_factory=lambda: custom_mock_compressor,
            session_factory=context_manager_session_factory,
        )

        result = await execute_planner_request(planner, test_db_session, test_user, test_project_id)

        # Verify result is valid
        assert result is not None

    @pytest.mark.usefixtures("test_user_token_config")
    async def test_planner_returns_context_package_directly_from_assembler(
        self,
        test_db_session,
        test_user,
        mock_compressor,
        context_manager_session_factory,
        test_project_id,
    ) -> None:
        """Test planner returns ContextPackage directly from AssemblerService without rebuilding."""
        doc1 = create_test_document("Document 1", 0.7, "test1.txt")
        doc2 = create_test_document("Document 2", 0.9, "test2.txt")
        docs = [doc1, doc2]

        mock_retriever = create_mock_retriever(docs)

        planner = ContextManagerPlanner(
            retriever_service_factory=create_retriever_factory(mock_retriever),
            compressor_service_factory=lambda: mock_compressor,
            session_factory=context_manager_session_factory,
        )

        result = await execute_planner_request(planner, test_db_session, test_user, test_project_id)

        # Verify ContextPackage has all AssemblerService-generated fields
        assert math.isclose(result.grounding_score, 0.8)  # (0.7 + 0.9) / 2

        # Verify citations from AssemblerService (now use FileMetadata.id UUIDs)
        assert len(result.citations) == 2
        assert str(doc1.file_metadata.id) in result.citations
        assert str(doc2.file_metadata.id) in result.citations

        # Verify payload was built by AssemblerService
        assert result.payload is not None
        assert "documents" in result.payload
        assert len(result.payload["documents"]) == 2
