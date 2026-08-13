"""Document conversion task for file processing.

This module provides the DocumentConversionTask class for converting uploaded
files to markdown format. The task is decoupled from invocation execution -
it only handles file conversion and updates FileMetadata status in the database.

Key design decisions:
- Uses FileManager for all FileMetadata operations (encapsulation principle)
- Does NOT trigger invocation execution (decoupled from InvocationService)
- Accepts file_id, not invocation_id
- Updates FileMetadata.status via FileManager.update_file_status()
"""

import contextlib
from collections.abc import AsyncGenerator, Callable
from uuid import UUID

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.database.session import get_db
from syntara.files.file_manager import FileManager, get_file_manager
from syntara.files.models import FileMetadata
from syntara.files.document_conversion.services.document_conversion_service import (
    DocumentConversionService,
)
from syntara.files.document_conversion.services.types import ConversionState
from syntara.files.models import FileStatus

logger = structlog.stdlib.get_logger(__name__)


class DocumentConversionTask:
    """Task handler for document conversion background processing.

    Converts uploaded files to markdown format and updates FileMetadata status
    in the database via FileManager. This task is decoupled from invocation
    execution - it only handles file conversion.

    The conversion flow:
    1. Get FileMetadata by file_id via FileManager
    2. Update status to CONVERTING
    3. Perform conversion
    4. Update status to CONVERTED (with converted_content_path) or CONVERSION_FAILED

    Note:
        This task does NOT trigger invocation execution. The InvocationService
        is responsible for orchestrating when to convert vs when to execute.

    """

    def __init__(
        self,
        file_manager_factory: Callable[[], FileManager] = get_file_manager,
        session_factory: Callable[[], AsyncGenerator[AsyncSession, None]] = get_db,
    ) -> None:
        """Initialize the document conversion task.

        Args:
            file_manager_factory: Factory function for FileManager
            session_factory: Factory function for creating database sessions

        """
        self.file_manager = file_manager_factory()
        self.session_factory = session_factory
        # Create DocumentConversionService with our FileManager
        self.service = DocumentConversionService(
            file_manager_factory=file_manager_factory,
        )
        # Create async context managers from factories
        self.get_async_session_context = contextlib.asynccontextmanager(session_factory)

    async def convert(self, file_id: UUID) -> ConversionState:
        """Background task to convert a single file to markdown format.

        This method:
        1. Gets FileMetadata by file_id from the database via FileManager
        2. Updates status to CONVERTING
        3. Performs the conversion
        4. Updates status to CONVERTED or CONVERSION_FAILED

        Args:
            file_id: UUID of the file to convert

        Returns:
            ConversionState indicating the result (SUCCESS, FAILED, SKIPPED)

        """
        logger.info("Starting document conversion", file_id=file_id)

        try:
            async with self.get_async_session_context() as session:
                # Get file metadata from database via FileManager
                file_metadata = await self.file_manager.get_file_metadata(file_id, session)
                if not file_metadata:
                    logger.error("File not found", file_id=file_id)
                    return ConversionState.FAILED

                # Skip if not pending conversion
                if file_metadata.status != FileStatus.PENDING_CONVERSION:
                    logger.info(
                        "Skipping file not pending conversion",
                        file_id=file_id,
                        status=file_metadata.status.value,
                    )
                    return ConversionState.SKIPPED

                # Create a status updater that uses FileManager
                async def status_updater(updated_metadata: FileMetadata) -> None:
                    # This is called by DocumentConversionService to update status
                    # We use FileManager.update_file_status() for encapsulation
                    async with self.get_async_session_context() as update_session:
                        await self.file_manager.update_file_status(
                            file_id=file_id,
                            status=updated_metadata.status,
                            session=update_session,
                            converted_content_path=updated_metadata.converted_content_path,
                            conversion_error=updated_metadata.conversion_error,
                        )

                # Perform conversion using the service
                logger.info(
                    "Converting file",
                    file_id=file_id,
                    filename=file_metadata.filename,
                    mime_type=file_metadata.mime_type,
                )

                result = await self.service.convert_file(file_metadata, status_updater=status_updater)

                logger.info(
                    "Document conversion completed",
                    file_id=file_id,
                    result=result.name,
                )
                return result

        except Exception:
            logger.exception("Error during document conversion", file_id=file_id)

            # Try to update status to FAILED
            try:
                async with self.get_async_session_context() as error_session:
                    await self.file_manager.update_file_status(
                        file_id=file_id,
                        status=FileStatus.CONVERSION_FAILED,
                        session=error_session,
                        conversion_error="Unexpected error during conversion",
                    )
            except Exception:
                logger.exception("Failed to update file status after error", file_id=file_id)

            return ConversionState.FAILED


# ===================================================
# Factory function for dependency injection
# ---------------------------------------------------


def get_document_conversion_task(
    session_factory: Callable[[], AsyncGenerator[AsyncSession, None]] = get_db,
) -> DocumentConversionTask:
    """Create a DocumentConversionTask instance with fresh dependencies.

    Args:
        session_factory: Session factory for database operations (defaults to get_db)

    Returns:
        DocumentConversionTask: Fresh task instance

    Example:
        # Default usage
        task = get_document_conversion_task()
        await task.convert(file_id)

        # With custom session factory (e.g., for testing)
        task = get_document_conversion_task(session_factory=test_db_factory)
        await task.convert(file_id)

    """
    return DocumentConversionTask(session_factory=session_factory)


# ===================================================
