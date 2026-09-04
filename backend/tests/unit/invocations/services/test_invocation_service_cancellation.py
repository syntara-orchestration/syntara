"""Unit tests for InvocationService cancellation functionality."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch
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


def _session_with_invocation(invocation: MagicMock, *, rowcount: int = 1) -> AsyncMock:
    mock_session = AsyncMock()
    mock_session.get.return_value = invocation
    mock_result = MagicMock()
    mock_result.rowcount = rowcount
    mock_session.exec = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.refresh = AsyncMock()
    return mock_session


class TestInvocationServiceCancellation:
    """Test core cancellation business logic."""

    @pytest.mark.asyncio
    async def test_cancel_invocation_success(self, mock_user) -> None:
        """Test successful cancellation of running invocation."""
        invocation_id = uuid4()

        mock_invocation = MagicMock()
        mock_invocation.created_by = mock_user.id
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.checkpoint_data = None
        mock_invocation.context_data = {"agent": "test-agent", "model": "test-model", "file_ids": []}
        mock_session = _session_with_invocation(mock_invocation)

        service = InvocationService(mock_session, mock_user)
        result = await service.cancel_invocation(invocation_id, "Test cancellation")

        assert result == CancellationResult.SUCCESS
        assert mock_invocation.status == InvocationStatus.CANCELLED
        mock_session.exec.assert_awaited_once()
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
        mock_session.exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_invocation_not_cancellable(self, mock_user) -> None:
        """Test cancellation when invocation is already completed."""
        mock_session = AsyncMock()
        service = InvocationService(mock_session, mock_user)
        invocation_id = uuid4()

        mock_invocation = MagicMock()
        mock_invocation.created_by = mock_user.id
        mock_invocation.status = InvocationStatus.COMPLETED
        mock_session.get.return_value = mock_invocation

        result = await service.cancel_invocation(invocation_id)

        assert result == CancellationResult.NOT_CANCELLABLE
        mock_session.commit.assert_not_called()
        mock_session.exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_loses_race_to_completion(self, mock_user) -> None:
        """Conditional UPDATE with rowcount 0 means completion won the race."""
        invocation_id = uuid4()
        mock_invocation = MagicMock()
        mock_invocation.created_by = mock_user.id
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.checkpoint_data = None
        mock_invocation.context_data = {"file_ids": []}

        mock_session = _session_with_invocation(mock_invocation, rowcount=0)

        async def _refresh_to_completed(_invocation: object) -> None:
            mock_invocation.status = InvocationStatus.COMPLETED

        mock_session.refresh = AsyncMock(side_effect=_refresh_to_completed)

        service = InvocationService(mock_session, mock_user)
        result = await service.cancel_invocation(invocation_id, "Test cancellation")

        assert result == CancellationResult.NOT_CANCELLABLE
        assert mock_invocation.status == InvocationStatus.COMPLETED
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_commit_failure_rolls_back(self, mock_user) -> None:
        """Commit failure rolls back so the request session stays usable."""
        invocation_id = uuid4()
        mock_invocation = MagicMock()
        mock_invocation.created_by = mock_user.id
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.checkpoint_data = None
        mock_invocation.context_data = {"file_ids": []}
        mock_session = _session_with_invocation(mock_invocation)
        mock_session.commit = AsyncMock(side_effect=Exception("DB Error"))

        service = InvocationService(mock_session, mock_user)
        with pytest.raises(Exception, match="DB Error"):
            await service.cancel_invocation(invocation_id, "Test")

        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_invocation_signals_via_redis(self, mock_user) -> None:
        """Test that cancellation signals the agent loop via Redis after DB commit."""
        invocation_id = uuid4()
        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.checkpoint_data = None
        mock_invocation.context_data = {"file_ids": []}
        mock_session = _session_with_invocation(mock_invocation)
        service = InvocationService(mock_session, mock_user)

        with patch.object(service, "_signal_cancellation", new=AsyncMock()) as mock_signal:
            result = await service.cancel_invocation(invocation_id, "test reason")

            assert result == CancellationResult.SUCCESS
            mock_session.commit.assert_called_once()
            mock_signal.assert_awaited_once_with(invocation_id)

    @pytest.mark.asyncio
    async def test_signal_cancellation_sets_redis_key_without_publishing(self, mock_user) -> None:
        """Test _signal_cancellation sets the cancel key but does not publish a terminal event."""
        mock_session = AsyncMock()
        service = InvocationService(mock_session, mock_user)
        invocation_id = uuid4()

        mock_client = AsyncMock()

        with patch("syntara.agent_orchestrator.services.invocation_service.StreamClient") as mock_stream_cls:
            mock_stream_cls.return_value.__aenter__.return_value = mock_client

            await service._signal_cancellation(invocation_id)

            # TTL matches Agent Execution timeout (3600s)
            mock_client.set_key.assert_awaited_once_with(f"invocation:{invocation_id}:cancelled", "1", 3600)
            mock_client.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_signal_cancellation_failure_does_not_prevent_cancellation(self, mock_user) -> None:
        """Test that _signal_cancellation swallows Redis errors without raising."""
        mock_session = AsyncMock()
        service = InvocationService(mock_session, mock_user)
        invocation_id = uuid4()

        with patch("syntara.agent_orchestrator.services.invocation_service.StreamClient") as mock_cls:
            mock_cls.return_value.__aenter__.side_effect = ConnectionError("Redis down")
            await service._signal_cancellation(invocation_id)

    @pytest.mark.asyncio
    async def test_cancel_with_files_calls_retriever_delete(self, mock_user) -> None:
        """Cancellation deletes files via the storage retriever."""
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
        mock_session = _session_with_invocation(mock_invocation)

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
    async def test_cancel_returns_success_when_cleanup_raises(self, mock_user) -> None:
        """A cleanup failure after DB commit must not 500 a successful cancel."""
        invocation_id = uuid4()
        mock_invocation = MagicMock()
        mock_invocation.id = invocation_id
        mock_invocation.status = InvocationStatus.RUNNING
        mock_invocation.checkpoint_data = None
        mock_invocation.context_data = {}
        mock_session = _session_with_invocation(mock_invocation)

        service = InvocationService(mock_session, mock_user)

        with (
            patch.object(service, "_signal_cancellation", new=AsyncMock()) as mock_signal,
            patch.object(service, "_cleanup_invocation_files", side_effect=RuntimeError("storage unavailable")),
        ):
            result = await service.cancel_invocation(invocation_id, "cleanup failure test")

        assert result == CancellationResult.SUCCESS
        mock_session.commit.assert_called_once()
        mock_signal.assert_awaited_once_with(invocation_id)

    @pytest.mark.asyncio
    async def test_cancel_cleanup_continues_on_single_file_error(self, mock_user) -> None:
        """File cleanup is best-effort: one failure doesn't block the rest."""
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
        mock_session = _session_with_invocation(mock_invocation)

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
