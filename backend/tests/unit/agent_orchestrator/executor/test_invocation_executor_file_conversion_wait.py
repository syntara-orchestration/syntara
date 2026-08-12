"""Unit tests for InvocationExecutor._wait_for_file_conversions."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.executor.invocation_executor import InvocationExecutor
from syntara.agent_orchestrator.models.context_data import InvocationContextData
from syntara.files.models import FileStatus


def _make_file_metadata(file_id: UUID, status: FileStatus, filename: str = "test.pdf") -> MagicMock:
    fm = MagicMock()
    fm.id = file_id
    fm.status = status
    fm.filename = filename
    return fm


def _make_ctx(file_ids: list[str] | None = None) -> InvocationContextData:
    return InvocationContextData.model_validate({"file_ids": file_ids or []})


class TestWaitForFileConversions:
    """Tests for the _wait_for_file_conversions polling method."""

    @pytest.fixture
    def executor(self):
        mock_session = AsyncMock()

        async def mock_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        return InvocationExecutor(session_factory=mock_session_factory)

    @pytest.mark.asyncio
    async def test_skip_when_no_file_ids(self, executor):
        ctx = _make_ctx()
        executor.file_manager.get_files_metadata = AsyncMock()
        await executor._wait_for_file_conversions(ctx)
        executor.file_manager.get_files_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_files_already_converted(self, executor):
        fid1, fid2 = uuid4(), uuid4()
        ctx = _make_ctx([str(fid1), str(fid2)])

        executor.file_manager.get_files_metadata = AsyncMock(
            return_value=[
                _make_file_metadata(fid1, FileStatus.CONVERTED),
                _make_file_metadata(fid2, FileStatus.CONVERTED),
            ]
        )

        await executor._wait_for_file_conversions(ctx)
        executor.file_manager.get_files_metadata.assert_called_once()

    @pytest.mark.asyncio
    async def test_waits_until_files_converted(self, executor):
        fid = uuid4()
        ctx = _make_ctx([str(fid)])

        executor.file_manager.get_files_metadata = AsyncMock(
            side_effect=[
                [_make_file_metadata(fid, FileStatus.PENDING_CONVERSION)],
                [_make_file_metadata(fid, FileStatus.CONVERTING)],
                [_make_file_metadata(fid, FileStatus.CONVERTED)],
            ]
        )

        with patch(
            "syntara.agent_orchestrator.executor.invocation_executor.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            await executor._wait_for_file_conversions(ctx)

        assert executor.file_manager.get_files_metadata.call_count == 3
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_mixed_terminal_states(self, executor):
        fid1, fid2 = uuid4(), uuid4()
        ctx = _make_ctx([str(fid1), str(fid2)])

        executor.file_manager.get_files_metadata = AsyncMock(
            return_value=[
                _make_file_metadata(fid1, FileStatus.CONVERTED),
                _make_file_metadata(fid2, FileStatus.CONVERSION_FAILED, "bad.docx"),
            ]
        )

        await executor._wait_for_file_conversions(ctx)
        executor.file_manager.get_files_metadata.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_proceeds_gracefully(self, executor):
        fid = uuid4()
        ctx = _make_ctx([str(fid)])

        executor.file_manager.get_files_metadata = AsyncMock(
            return_value=[_make_file_metadata(fid, FileStatus.CONVERTING)]
        )

        call_count = 0

        def advancing_monotonic() -> float:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return 0.0
            return 999.0

        with (
            patch(
                "syntara.agent_orchestrator.executor.invocation_executor.time.monotonic",
                side_effect=advancing_monotonic,
            ),
            patch("syntara.agent_orchestrator.executor.invocation_executor.asyncio.sleep", new_callable=AsyncMock),
        ):
            await executor._wait_for_file_conversions(ctx)

        assert executor.file_manager.get_files_metadata.call_count >= 2

    @pytest.mark.asyncio
    async def test_exponential_backoff(self, executor):
        fid = uuid4()
        ctx = _make_ctx([str(fid)])

        poll_count = 0

        async def side_effect(*_args: object, **_kwargs: object) -> list[MagicMock]:
            nonlocal poll_count
            poll_count += 1
            if poll_count < 5:
                return [_make_file_metadata(fid, FileStatus.CONVERTING)]
            return [_make_file_metadata(fid, FileStatus.CONVERTED)]

        executor.file_manager.get_files_metadata = AsyncMock(side_effect=side_effect)

        with patch(
            "syntara.agent_orchestrator.executor.invocation_executor.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            await executor._wait_for_file_conversions(ctx)

        sleep_values = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_values == pytest.approx([0.5, 1.0, 2.0, 4.0])
