"""Unit tests for FileManager.delete_file and is_project_deleted."""

from unittest.mock import AsyncMock, MagicMock, Mock, call
from uuid import uuid4

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.files.exceptions import FileError
from syntara.files.file_manager import FileManager
from syntara.files.models import FileMetadata, FileStatus


@pytest.fixture
def mock_retriever() -> AsyncMock:
    """Return a retriever mock with a successful delete_file."""
    retriever = AsyncMock()
    retriever.delete_file = AsyncMock(return_value=True)
    return retriever


@pytest.fixture
def file_manager_with_retriever(mock_retriever: AsyncMock) -> FileManager:
    """Return a FileManager with a mocked storage retriever."""
    manager = FileManager.__new__(FileManager)
    manager.settings = MagicMock()
    manager._retriever = mock_retriever
    return manager


class TestFileManagerDeleteFile:
    """Tests for FileManager.delete_file storage and metadata cleanup."""

    @pytest.mark.asyncio
    async def test_delete_file_removes_storage_and_metadata(
        self,
        file_manager_with_retriever: FileManager,
        mock_retriever: AsyncMock,
    ) -> None:
        metadata = FileMetadata(
            id=uuid4(),
            filename="doc.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            file_path="file-id-doc.pdf",
            converted_content_path="file-id-content.md",
            status=FileStatus.CONVERTED,
            project_id=uuid4(),
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=metadata)
        session.delete = AsyncMock()
        session.commit = AsyncMock()

        result = await file_manager_with_retriever.delete_file(metadata.id, session)

        assert result is metadata
        assert mock_retriever.delete_file.await_count == 2
        mock_retriever.delete_file.assert_has_awaits([call("file-id-doc.pdf"), call("file-id-content.md")])
        session.delete.assert_awaited_once_with(metadata)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_file_deletes_metadata_before_storage(
        self,
        file_manager_with_retriever: FileManager,
        mock_retriever: AsyncMock,
    ) -> None:
        metadata = FileMetadata(
            id=uuid4(),
            filename="doc.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            file_path="file-id-doc.pdf",
            converted_content_path=None,
            status=FileStatus.CONVERTED,
            project_id=uuid4(),
        )
        order: list[str] = []
        session = AsyncMock()
        session.get = AsyncMock(return_value=metadata)

        async def track_delete(_metadata: FileMetadata) -> None:
            order.append("db_delete")

        async def track_commit() -> None:
            order.append("db_commit")

        async def track_storage_delete(_path: str) -> bool:
            order.append("s3_delete")
            return True

        session.delete = AsyncMock(side_effect=track_delete)
        session.commit = AsyncMock(side_effect=track_commit)
        mock_retriever.delete_file = AsyncMock(side_effect=track_storage_delete)

        await file_manager_with_retriever.delete_file(metadata.id, session)

        assert order == ["db_delete", "db_commit", "s3_delete"]

    @pytest.mark.asyncio
    async def test_delete_file_not_found_raises(
        self,
        file_manager_with_retriever: FileManager,
        mock_retriever: AsyncMock,
    ) -> None:
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)

        with pytest.raises(SafeValueError, match="File not found"):
            await file_manager_with_retriever.delete_file(uuid4(), session)

        mock_retriever.delete_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_file_continues_if_converted_cleanup_fails(
        self,
        file_manager_with_retriever: FileManager,
        mock_retriever: AsyncMock,
    ) -> None:
        metadata = FileMetadata(
            id=uuid4(),
            filename="doc.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            file_path="file-id-doc.pdf",
            converted_content_path="file-id-content.md",
            status=FileStatus.CONVERTED,
            project_id=uuid4(),
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=metadata)
        session.delete = AsyncMock()
        session.commit = AsyncMock()
        mock_retriever.delete_file = AsyncMock(side_effect=[True, FileError("converted missing")])

        await file_manager_with_retriever.delete_file(metadata.id, session)

        session.delete.assert_awaited_once_with(metadata)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_file_continues_if_primary_storage_cleanup_fails(
        self,
        file_manager_with_retriever: FileManager,
        mock_retriever: AsyncMock,
    ) -> None:
        metadata = FileMetadata(
            id=uuid4(),
            filename="doc.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            file_path="file-id-doc.pdf",
            converted_content_path="file-id-content.md",
            status=FileStatus.CONVERTED,
            project_id=uuid4(),
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=metadata)
        session.delete = AsyncMock()
        session.commit = AsyncMock()
        mock_retriever.delete_file = AsyncMock(side_effect=[FileError("object missing"), True])

        result = await file_manager_with_retriever.delete_file(metadata.id, session)

        assert result is metadata
        session.delete.assert_awaited_once_with(metadata)
        session.commit.assert_awaited_once()
        assert mock_retriever.delete_file.await_count == 2


class TestFileManagerIsProjectDeleted:
    """Tests for FileManager.is_project_deleted orphan detection."""

    @pytest.mark.asyncio
    async def test_is_project_deleted_true_when_deleted_at_set(self, file_manager_with_retriever: FileManager) -> None:
        from datetime import UTC, datetime

        project = Mock()
        project.deleted_at = datetime.now(UTC)
        session = AsyncMock()
        result = Mock()
        result.one_or_none = Mock(return_value=project)
        session.exec = AsyncMock(return_value=result)

        assert await file_manager_with_retriever.is_project_deleted(uuid4(), session) is True

    @pytest.mark.asyncio
    async def test_is_project_deleted_false_when_active(self, file_manager_with_retriever: FileManager) -> None:
        project = Mock()
        project.deleted_at = None
        session = AsyncMock()
        result = Mock()
        result.one_or_none = Mock(return_value=project)
        session.exec = AsyncMock(return_value=result)

        assert await file_manager_with_retriever.is_project_deleted(uuid4(), session) is False

    @pytest.mark.asyncio
    async def test_is_project_deleted_true_when_project_missing(self, file_manager_with_retriever: FileManager) -> None:
        """Hard-deleted/missing projects must be treated as deleted orphans."""
        session = AsyncMock()
        result = Mock()
        result.one_or_none = Mock(return_value=None)
        session.exec = AsyncMock(return_value=result)

        assert await file_manager_with_retriever.is_project_deleted(uuid4(), session) is True


class TestFileManagerBatchIsProjectDeleted:
    """Tests for FileManager.batch_is_project_deleted orphan detection."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "scenario",
        [
            pytest.param("empty", id="empty-set-short-circuit"),
            pytest.param("mapped", id="in-query-mapping"),
            pytest.param("missing", id="missing-id-deleted-default"),
        ],
    )
    async def test_batch_is_project_deleted(
        self,
        file_manager_with_retriever: FileManager,
        scenario: str,
    ) -> None:
        from datetime import UTC, datetime

        active_id = uuid4()
        soft_id = uuid4()
        missing_id = uuid4()

        active = Mock()
        active.id = active_id
        active.deleted_at = None

        soft = Mock()
        soft.id = soft_id
        soft.deleted_at = datetime.now(UTC)

        session = AsyncMock()
        query_result = Mock()

        if scenario == "empty":
            result = await file_manager_with_retriever.batch_is_project_deleted(set(), session)
            assert result == {}
            session.exec.assert_not_called()
            return

        if scenario == "mapped":
            query_result.all = Mock(return_value=[active, soft])
            session.exec = AsyncMock(return_value=query_result)
            result = await file_manager_with_retriever.batch_is_project_deleted({active_id, soft_id}, session)
            assert result == {active_id: False, soft_id: True}
            session.exec.assert_awaited_once()
            return

        query_result.all = Mock(return_value=[active])
        session.exec = AsyncMock(return_value=query_result)
        result = await file_manager_with_retriever.batch_is_project_deleted({active_id, missing_id}, session)
        assert result == {active_id: False, missing_id: True}
        session.exec.assert_awaited_once()
