"""Unit tests for InvocationService cancellation functionality."""

from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.models import InvocationStatus
from syntara.agent_orchestrator.models.request import CancellationResult
from syntara.agent_orchestrator.services.invocation_service import InvocationService
from syntara.files.models import FileMetadata


@pytest.fixture
def mock_user() -> MagicMock:
    """Lightweight mock user for unit tests that don't need a real DB."""
    user = MagicMock()
    user.id = uuid4()
    return user


class TestInvocationServiceCancellation:
    """Test core cancellation business logic."""

    @pytest.mark.asyncio
    async def test_cancel_invocation_success(self, mock_user) -> None:
        """Test successful cancellation of running invocation."""
        mock_session = AsyncMock()
        service = InvocationService(mock_session, mock_user)
        invocation_id = uuid4()

        # Setup: Running invocation owned by user
        mock_invocation = MagicMock()
        mock_invocation.created_by = mock_user.id
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.checkpoint_data = None
        mock_invocation.context_data = {"agent": "test-agent", "model": "test-model", "file_ids": []}
        mock_session.get.return_value = mock_invocation

        result = await service.cancel_invocation(invocation_id, "Test cancellation")

        assert result == CancellationResult.SUCCESS
        assert mock_invocation.status == InvocationStatus.CANCELLED
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_invocation_not_found(self, mock_user) -> None:
        """Test cancellation when invocation doesn't exist."""
        mock_session = AsyncMock()
        service = InvocationService(mock_session, mock_user)
        invocation_id = uuid4()

        mock_session.get.return_value = None

        result = await service.cancel_invocation(invocation_id)

        assert result == CancellationResult.NOT_FOUND
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_invocation_not_cancellable(self, mock_user) -> None:
        """Test cancellation when invocation is already completed."""
        mock_session = AsyncMock()
        service = InvocationService(mock_session, mock_user)
        invocation_id = uuid4()

        # Setup: Completed invocation owned by user
        mock_invocation = MagicMock()
        mock_invocation.created_by = mock_user.id
        mock_invocation.status = InvocationStatus.COMPLETED
        mock_session.get.return_value = mock_invocation

        result = await service.cancel_invocation(invocation_id)

        assert result == CancellationResult.NOT_CANCELLABLE
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_with_files_calls_retriever_delete(self, mock_user) -> None:
        """Cancellation deletes files via the storage retriever."""
        mock_session = AsyncMock()
        file_id_1 = uuid4()
        file_id_2 = uuid4()
        invocation_id = uuid4()

        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.checkpoint_data = None
        mock_invocation.context_data = {
            "agent": "test-agent",
            "model": "test-model",
            "file_ids": [str(file_id_1), str(file_id_2)],
        }
        mock_session.get.return_value = mock_invocation

        mock_file_metadata = [
            FileMetadata(
                id=file_id_1,
                filename="report.pdf",
                mime_type="application/pdf",
                size_bytes=1024,
                file_path="orchestrator-abc-report.pdf",
                converted_content_path="orchestrator-abc-content.md",
            ),
            FileMetadata(
                id=file_id_2,
                filename="data.txt",
                mime_type="text/plain",
                size_bytes=512,
                file_path="orchestrator-def-data.txt",
            ),
        ]

        mock_retriever = AsyncMock()
        mock_retriever.delete_file = AsyncMock(return_value=True)
        mock_file_manager = Mock()
        mock_file_manager.get_files_metadata = AsyncMock(return_value=mock_file_metadata)
        mock_file_manager.get_retriever = Mock(return_value=mock_retriever)

        service = InvocationService(mock_session, mock_user, file_manager_factory=lambda: mock_file_manager)
        result = await service.cancel_invocation(invocation_id, "cleanup test")

        assert result == CancellationResult.SUCCESS
        assert mock_retriever.delete_file.call_count == 3
        deleted_paths = [c.args[0] for c in mock_retriever.delete_file.call_args_list]
        assert deleted_paths == [
            "orchestrator-abc-report.pdf",
            "orchestrator-abc-content.md",
            "orchestrator-def-data.txt",
        ]

    @pytest.mark.asyncio
    async def test_cancel_cleanup_continues_on_single_file_error(self, mock_user) -> None:
        """File cleanup is best-effort: one failure doesn't block the rest."""
        mock_session = AsyncMock()
        file_id_1 = uuid4()
        file_id_2 = uuid4()
        invocation_id = uuid4()

        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.checkpoint_data = None
        mock_invocation.context_data = {
            "agent": "test-agent",
            "model": "test-model",
            "file_ids": [str(file_id_1), str(file_id_2)],
        }
        mock_session.get.return_value = mock_invocation

        mock_file_metadata = [
            FileMetadata(
                id=file_id_1,
                filename="bad.pdf",
                mime_type="application/pdf",
                size_bytes=1024,
                file_path="orchestrator-aaa-bad.pdf",
            ),
            FileMetadata(
                id=file_id_2,
                filename="good.txt",
                mime_type="text/plain",
                size_bytes=512,
                file_path="orchestrator-bbb-good.txt",
            ),
        ]

        mock_retriever = AsyncMock()
        mock_retriever.delete_file = AsyncMock(side_effect=[Exception("S3 error"), True])
        mock_file_manager = Mock()
        mock_file_manager.get_files_metadata = AsyncMock(return_value=mock_file_metadata)
        mock_file_manager.get_retriever = Mock(return_value=mock_retriever)

        service = InvocationService(mock_session, mock_user, file_manager_factory=lambda: mock_file_manager)
        result = await service.cancel_invocation(invocation_id, "partial failure test")

        assert result == CancellationResult.SUCCESS
        assert mock_retriever.delete_file.call_count == 2
        mock_retriever.delete_file.assert_any_call("orchestrator-bbb-good.txt")
