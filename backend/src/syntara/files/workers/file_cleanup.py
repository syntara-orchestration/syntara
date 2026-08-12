"""Periodic cleanup of stale S3 multipart uploads."""

from __future__ import annotations

from functools import lru_cache

import structlog

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.workers.periodic import PeriodicWorker
from syntara.files.audit.file_cleaned_up import FileCleanedUpEvent
from syntara.files.file_manager import get_file_manager
from syntara.files.retrievers.s3 import S3FileRetriever

logger = structlog.stdlib.get_logger(__name__)

MULTIPART_CLEANUP_INTERVAL_SECONDS = 3600.0


async def cleanup_stale_multipart_uploads(
    session_factory: object,  # noqa: ARG001
) -> None:
    """Abort stale S3 multipart uploads that were never completed."""
    settings = get_settings()
    file_manager = get_file_manager()

    if not file_manager.s3_configured:
        return

    retriever = file_manager.get_retriever()
    multipart_aborted = 0
    if isinstance(retriever, S3FileRetriever):
        multipart_aborted = await retriever.cleanup_stale_multipart_uploads(
            threshold_hours=settings.file_multipart_cleanup_threshold_hours,
        )

    if multipart_aborted:
        logger.info(
            "multipart_cleanup_completed",
            multipart_uploads_aborted=multipart_aborted,
        )
        AuditEventDispatcher.dispatch(
            FileCleanedUpEvent(
                files_deleted=0,
                multipart_uploads_aborted=multipart_aborted,
            ),
        )


@lru_cache(maxsize=1)
def get_multipart_cleanup_worker() -> PeriodicWorker:
    """Create the periodic multipart cleanup worker."""
    return PeriodicWorker(
        name="s3-multipart-cleanup",
        interval_seconds=MULTIPART_CLEANUP_INTERVAL_SECONDS,
        session_factory=AsyncSessionLocal,
        callback=cleanup_stale_multipart_uploads,
        coordinate=True,
    )
