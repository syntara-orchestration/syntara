"""File storage health check utilities.

Provides startup validation and runtime health probes for S3 storage.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import TYPE_CHECKING

import structlog

from syntara.files.file_manager import get_file_manager

if TYPE_CHECKING:
    from syntara.core.config.base import Settings

logger = structlog.stdlib.get_logger(__name__)

HEALTH_CHECK_TIMEOUT_SECONDS = 10


class FileStorageStatus(StrEnum):
    """Availability of the S3-compatible object storage backend."""

    OK = "ok"
    """Configured and reachable."""

    DEGRADED = "degraded"
    """Configured but the reachability probe failed or timed out."""

    UNCONFIGURED = "unconfigured"
    """``APP_S3_ENDPOINT_URL`` is not set; file uploads are disabled."""

    ERROR = "error"
    """The probe raised an unexpected exception."""


async def validate_file_storage_at_startup(settings: Settings) -> None:
    """Validate S3 file storage reachability at startup.

    Logs a warning if S3 is not configured or unreachable.
    Does NOT raise — the app starts without S3, and file upload
    endpoints return 503 until S3 is available.
    """
    file_manager = get_file_manager()
    if not file_manager.s3_configured:
        logger.warning(
            "No S3 storage configured — file uploads will be unavailable until APP_S3_ENDPOINT_URL is set",
        )
        return

    try:
        healthy = await asyncio.wait_for(
            file_manager.get_retriever().health_check(),
            timeout=HEALTH_CHECK_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        healthy = False

    if not healthy:
        logger.warning(
            "S3 file storage not reachable — file uploads will be unavailable",
            endpoint_url=settings.s3_endpoint_url,
            bucket_name=settings.s3_bucket_name,
        )
    else:
        logger.info("S3 file storage connected", bucket_name=settings.s3_bucket_name)


async def check_file_storage_health() -> FileStorageStatus:
    """Probe S3 file storage.

    Never raises — all failures are caught and mapped to a status value.
    """
    try:
        file_manager = get_file_manager()
        if not file_manager.s3_configured:
            return FileStorageStatus.UNCONFIGURED
        healthy = await asyncio.wait_for(
            file_manager.get_retriever().health_check(),
            timeout=HEALTH_CHECK_TIMEOUT_SECONDS,
        )
        return FileStorageStatus.OK if healthy else FileStorageStatus.DEGRADED
    except TimeoutError:
        logger.debug("Health check: file storage timed out")
        return FileStorageStatus.DEGRADED
    except Exception:  # noqa: BLE001
        logger.debug("Health check: file storage check failed", exc_info=True)
        return FileStorageStatus.ERROR
