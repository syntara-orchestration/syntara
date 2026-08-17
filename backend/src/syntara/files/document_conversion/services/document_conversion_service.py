"""Document conversion service for managing conversion operations.

This module provides the main service for coordinating document conversion
operations with file manager integration and status management.
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.exceptions import SafeValueError
from syntara.files.audit.file_converted import ConversionStateAudit, FileConvertedEvent
from syntara.files.document_conversion.models.conversion_config import ConversionConfig
from syntara.files.document_conversion.registry import (
    ConverterRegistry,
    get_converter_registry,
)
from syntara.files.document_conversion.services.types import ConversionState
from syntara.files.file_manager import FileManager, get_file_manager
from syntara.files.models import FileMetadata, FileStatus

if TYPE_CHECKING:
    from syntara.files.document_conversion.models import ConversionResult

logger = structlog.stdlib.get_logger(__name__)


class DocumentConversionService:
    """Main service for document conversion operations with FileMetadata integration.

    Coordinates conversion operations by:
    - Loading file content via retrievers
    - Finding appropriate converters by MIME type
    - Managing conversion status and metadata updates
    - Storing converted content back via retrievers
    """

    def __init__(
        self,
        file_manager_factory: Callable[[], FileManager] = get_file_manager,
        converter_registry_factory: Callable[[], ConverterRegistry] = get_converter_registry,
    ) -> None:
        """Initialize the document conversion service.

        Args:
            file_manager_factory: Factory function for creating FileManager
            converter_registry_factory: Factory function for creating ConverterRegistry

        """
        self.file_manager = file_manager_factory()
        self.converter_registry = converter_registry_factory()

    @staticmethod
    def _generate_output_filename(original_filename: str) -> str:
        """Generate output filename for converted markdown file.

        Args:
            original_filename: Original source filename

        Returns:
            Output filename with .md extension

        Example:
            assert DocumentConversionService._generate_output_filename("doc.pdf") == "doc.md"
            assert DocumentConversionService._generate_output_filename("file.docx") == "file.md"

        """
        # Extract base name without extension and add .md
        base_name = Path(original_filename).stem
        return f"{base_name}.md"

    async def _store_converted_file(
        self, file_metadata: "FileMetadata", conversion_result: "ConversionResult"
    ) -> tuple[str, str]:
        output_filename = DocumentConversionService._generate_output_filename(file_metadata.filename)

        if conversion_result.converted_content is None:
            msg = "Cannot store file: conversion result has no content"
            raise SafeValueError(msg)

        # Get retriever for saving converted file
        output_retriever = self.file_manager.get_retriever()

        # Use orchestrator-{file_id}-content.md to match FileMetadata convention
        # and avoid collisions when multiple files share the same stem
        storage_key = f"orchestrator-{file_metadata.id}-content.md"

        output_path: str = await output_retriever.save_file(
            conversion_result.converted_content.encode("utf-8"), storage_key
        )
        return output_filename, output_path

    @staticmethod
    async def _successful_conversion(
        file_metadata: "FileMetadata",
        conversion_result: "ConversionResult",
        status_updater: Callable[[FileMetadata], Awaitable[None]],
        *,
        operation_id: str,
        output_path: str,
        output_filename: str,
        converter_name: str,
    ) -> None:
        logger.info(
            "Document conversion succeeded",
            operation_id=operation_id,
            filename=file_metadata.filename,
            duration_ms=conversion_result.conversion_time_ms,
            converter=converter_name,
            output=output_filename,
        )

        file_metadata.status = FileStatus.CONVERTED
        file_metadata.converted_content_path = output_path

        # Update Invocation record
        await status_updater(file_metadata)

    @staticmethod
    async def _fail_conversion(
        file_metadata: "FileMetadata",
        conversion_result: "ConversionResult",
        status_updater: Callable[[FileMetadata], Awaitable[None]],
        *,
        operation_id: str,
        converter_name: str,
    ) -> None:
        logger.error(
            "Document conversion failed",
            operation_id=operation_id,
            filename=file_metadata.filename,
            converter=converter_name,
            error=conversion_result.error_message,
        )

        # Update status to conversion_failed
        file_metadata.status = FileStatus.CONVERSION_FAILED
        file_metadata.conversion_error = conversion_result.error_message

        await status_updater(file_metadata)

    @staticmethod
    async def _fail_conversion_exception(
        file_metadata: "FileMetadata",
        status_updater: Callable[[FileMetadata], Awaitable[None]],
        operation_id: str,
    ) -> None:
        logger.exception(
            "Unexpected error during document conversion",
            operation_id=operation_id,
            filename=file_metadata.filename,
        )

        # Update status to conversion_failed with error details
        file_metadata.status = FileStatus.CONVERSION_FAILED
        file_metadata.conversion_error = "Unexpected error during conversion."

        await status_updater(file_metadata)

    @staticmethod
    async def _fail_conversion_missing_converter(
        file_metadata: "FileMetadata", operation_id: str, status_updater: Callable[[FileMetadata], Awaitable[None]]
    ) -> None:
        logger.warning(
            "No converter available for MIME type",
            operation_id=operation_id,
            mime_type=file_metadata.mime_type,
        )

        # Update status to conversion_failed
        file_metadata.status = FileStatus.CONVERSION_FAILED
        file_metadata.conversion_error = f"Unsupported MIME type: {file_metadata.mime_type}"

        # Update Invocation record
        await status_updater(file_metadata)

    async def convert_file(
        self, file_metadata: "FileMetadata", status_updater: Callable[[FileMetadata], Awaitable[None]]
    ) -> ConversionState:
        """Convert a single FileMetadata object and return updated metadata.

        Args:
            file_metadata: FileMetadata object with status='pending_conversion'
            status_updater: Callback to update Invocation FileMetadata

        Returns:
            ConversionState enum with conversion state

        Example:
            service = DocumentConversionService(registry, config, file_manager)
            conversion_state = await service.convert_file(file_metadata, status_updater)
            assert conversion_state == ConversionState.SUCCESS

        """
        # Validate input status
        if file_metadata.status != FileStatus.PENDING_CONVERSION:
            logger.info(
                "Skipping file not pending conversion",
                filename=file_metadata.filename,
                status=file_metadata.status,
            )
            # Dispatch audit event for skipped conversion
            AuditEventDispatcher.dispatch(
                FileConvertedEvent(
                    file_id=file_metadata.id,
                    filename=file_metadata.filename,
                    mime_type=file_metadata.mime_type,
                    size_bytes=file_metadata.size_bytes,
                    conversion_state=ConversionStateAudit.SKIPPED,
                )
            )
            return ConversionState.SKIPPED

        # Check overwrite_existing setting
        config = await ConversionConfig.from_settings()
        if not config.overwrite_existing and file_metadata.converted_content_path is not None:
            logger.info(
                "Skipping conversion, file already converted and overwrite_existing is disabled",
                filename=file_metadata.filename,
                converted_content_path=file_metadata.converted_content_path,
            )
            file_metadata.status = FileStatus.CONVERTED
            await status_updater(file_metadata)
            AuditEventDispatcher.dispatch(
                FileConvertedEvent(
                    file_id=file_metadata.id,
                    filename=file_metadata.filename,
                    mime_type=file_metadata.mime_type,
                    size_bytes=file_metadata.size_bytes,
                    conversion_state=ConversionStateAudit.SKIPPED,
                )
            )
            return ConversionState.SKIPPED

        # Generate operation ID for logging and tracking
        operation_id = f"conv-{uuid4().hex[:8]}"

        logger.info(
            "Starting document conversion",
            operation_id=operation_id,
            filename=file_metadata.filename,
            mime_type=file_metadata.mime_type,
        )

        # Update status to 'converting'
        file_metadata.status = FileStatus.CONVERTING
        await status_updater(file_metadata)

        # Get appropriate retriever for loading source file
        retriever = self.file_manager.get_retriever()

        try:
            # Load file content via retriever
            file_content = await retriever.load_file(file_metadata.file_path)

            # Get converter for MIME type
            converter = self.converter_registry.get_converter(file_metadata.mime_type)
            if converter is None:
                await DocumentConversionService._fail_conversion_missing_converter(
                    file_metadata, operation_id, status_updater
                )
                # Dispatch audit event for missing converter
                AuditEventDispatcher.dispatch(
                    FileConvertedEvent(
                        file_id=file_metadata.id,
                        filename=file_metadata.filename,
                        mime_type=file_metadata.mime_type,
                        size_bytes=file_metadata.size_bytes,
                        conversion_state=ConversionStateAudit.FAILED,
                        error_type="UnsupportedFormatError",
                    )
                )
                return ConversionState.FAILED

            # Perform conversion with timeout
            logger.debug(
                "Using converter for file",
                converter=converter.get_converter_name(),
                filename=file_metadata.filename,
                operation_id=operation_id,
            )
            conversion_result = await converter.convert_with_timeout(file_content, file_metadata)

            # Manage conversion result
            if conversion_result.success:
                output_filename, output_path = await self._store_converted_file(file_metadata, conversion_result)
                await DocumentConversionService._successful_conversion(
                    file_metadata,
                    conversion_result,
                    status_updater,
                    operation_id=operation_id,
                    output_filename=output_filename,
                    output_path=output_path,
                    converter_name=converter.get_converter_name(),
                )
                # Dispatch audit event for successful conversion
                AuditEventDispatcher.dispatch(
                    FileConvertedEvent(
                        file_id=file_metadata.id,
                        filename=file_metadata.filename,
                        mime_type=file_metadata.mime_type,
                        size_bytes=file_metadata.size_bytes,
                        conversion_state=ConversionStateAudit.SUCCESS,
                        conversion_time_ms=conversion_result.conversion_time_ms,
                    )
                )
                return ConversionState.SUCCESS

            await DocumentConversionService._fail_conversion(
                file_metadata,
                conversion_result,
                status_updater,
                operation_id=operation_id,
                converter_name=converter.get_converter_name(),
            )
            # Dispatch audit event for failed conversion
            AuditEventDispatcher.dispatch(
                FileConvertedEvent(
                    file_id=file_metadata.id,
                    filename=file_metadata.filename,
                    mime_type=file_metadata.mime_type,
                    size_bytes=file_metadata.size_bytes,
                    conversion_state=ConversionStateAudit.FAILED,
                    conversion_time_ms=conversion_result.conversion_time_ms,
                    error_type="ConversionFailureError",
                )
            )
            return ConversionState.FAILED

        except (OSError, ValueError, RuntimeError):
            await DocumentConversionService._fail_conversion_exception(file_metadata, status_updater, operation_id)
            # Dispatch audit event for exception-based failure
            AuditEventDispatcher.dispatch(
                FileConvertedEvent(
                    file_id=file_metadata.id,
                    filename=file_metadata.filename,
                    mime_type=file_metadata.mime_type,
                    size_bytes=file_metadata.size_bytes,
                    conversion_state=ConversionStateAudit.FAILED,
                    error_type="ConversionFailureError",
                )
            )

        return ConversionState.FAILED


# ===================================================
# Generator for dependency injection
# ---------------------------------------------------


def get_document_conversion_service() -> DocumentConversionService:
    """Create a DocumentConversionService instance with fresh dependencies.

    Returns:
        DocumentConversionService: Fresh service instance

    Example:
        service = get_document_conversion_service()
        conversion_state = await service.convert_file(file_metadata, status_updater)

    """
    return DocumentConversionService()


# ===================================================
