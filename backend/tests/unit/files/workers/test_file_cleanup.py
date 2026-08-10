"""Unit tests for the periodic multipart cleanup worker."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.core.workers.periodic import PeriodicWorker
from syntara.files.audit.file_cleaned_up import FileCleanedUpEvent
from syntara.files.retrievers.s3 import S3FileRetriever
from syntara.files.workers.file_cleanup import cleanup_stale_multipart_uploads, get_multipart_cleanup_worker

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager


class TestCleanupStaleMultipartUploads:
    """Tests for the cleanup_stale_multipart_uploads callback."""

    @pytest.mark.asyncio
    async def test_s3_multipart_cleanup_runs(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        mock_s3_retriever = AsyncMock(spec=S3FileRetriever)
        mock_s3_retriever.cleanup_stale_multipart_uploads = AsyncMock(return_value=3)
        mock_fm = MagicMock()
        mock_fm.s3_configured = True
        mock_fm.get_retriever.return_value = mock_s3_retriever

        with (
            override_settings(file_multipart_cleanup_threshold_hours=48),
            patch("syntara.files.workers.file_cleanup.get_file_manager", return_value=mock_fm),
            patch("syntara.files.workers.file_cleanup.AuditEventDispatcher") as mock_dispatcher,
        ):
            await cleanup_stale_multipart_uploads(MagicMock())

        mock_s3_retriever.cleanup_stale_multipart_uploads.assert_called_once_with(threshold_hours=48)
        mock_dispatcher.dispatch.assert_called_once()
        event = mock_dispatcher.dispatch.call_args[0][0]
        assert isinstance(event, FileCleanedUpEvent)
        assert event.multipart_uploads_aborted == 3

    @pytest.mark.asyncio
    async def test_skips_when_s3_unconfigured(self) -> None:
        mock_fm = MagicMock()
        mock_fm.s3_configured = False

        with (
            patch("syntara.files.workers.file_cleanup.get_file_manager", return_value=mock_fm),
            patch("syntara.files.workers.file_cleanup.AuditEventDispatcher") as mock_dispatcher,
        ):
            await cleanup_stale_multipart_uploads(MagicMock())

        mock_dispatcher.dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_audit_when_nothing_aborted(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        mock_s3_retriever = AsyncMock(spec=S3FileRetriever)
        mock_s3_retriever.cleanup_stale_multipart_uploads = AsyncMock(return_value=0)
        mock_fm = MagicMock()
        mock_fm.s3_configured = True
        mock_fm.get_retriever.return_value = mock_s3_retriever

        with (
            override_settings(file_multipart_cleanup_threshold_hours=24),
            patch("syntara.files.workers.file_cleanup.get_file_manager", return_value=mock_fm),
            patch("syntara.files.workers.file_cleanup.AuditEventDispatcher") as mock_dispatcher,
        ):
            await cleanup_stale_multipart_uploads(MagicMock())

        mock_dispatcher.dispatch.assert_not_called()


class TestGetMultipartCleanupWorker:
    """Tests for the get_multipart_cleanup_worker factory."""

    def test_creates_worker_with_correct_config(self) -> None:
        with patch("syntara.files.workers.file_cleanup.AsyncSessionLocal", new_callable=MagicMock):
            get_multipart_cleanup_worker.cache_clear()
            worker = get_multipart_cleanup_worker()

        assert isinstance(worker, PeriodicWorker)
        assert worker._name == "s3-multipart-cleanup"
        assert worker._coordinate is True

    def test_returns_cached_singleton(self) -> None:
        with patch("syntara.files.workers.file_cleanup.AsyncSessionLocal", new_callable=MagicMock):
            get_multipart_cleanup_worker.cache_clear()
            w1 = get_multipart_cleanup_worker()
            w2 = get_multipart_cleanup_worker()
        assert w1 is w2
