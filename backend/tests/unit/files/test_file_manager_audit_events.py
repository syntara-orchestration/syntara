"""Integration tests for audit event emission from files domain services.

These tests verify that service methods correctly dispatch domain events
which are then converted to AuditEvents by the registered handlers.
"""

from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import EventSeverity, EventStatus
from syntara.files.audit.file_converted import ConversionStateAudit
from syntara.files.document_conversion.models.conversion_result import ConversionResult
from syntara.files.document_conversion.services import ConversionState
from syntara.files.document_conversion.services.document_conversion_service import (
    DocumentConversionService,
)
from syntara.files.exceptions import FileValidationError
from syntara.files.file_manager import FileManager
from syntara.files.models import FileMetadata, FileStatus

if TYPE_CHECKING:
    from fastapi import UploadFile

    from syntara.audit.models.audit_event import AuditEvent


class TestFileManagerAuditEvents:
    """Tests for audit event emission from FileManager.validate_and_save_files()."""

    def setup_method(self) -> None:
        """Register files audit handlers before each test."""
        from syntara.files.audit.files_uploaded import (
            FilesUploadedEvent,
            FilesUploadedHandler,
        )

        AuditEventDispatcher.register({FilesUploadedEvent: FilesUploadedHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_validate_and_save_files_success_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
    ) -> None:
        """Successful file upload should emit FilesUploadedEvent with file details."""
        # Arrange
        file_content = b"PDF content"

        async def _consume_stream(stream: AsyncGenerator[bytes], path: str) -> tuple[str, int]:
            total = 0
            async for chunk in stream:
                total += len(chunk)
            return "orchestrator-uuid-test.pdf", total

        file_manager = FileManager()
        mock_retriever = AsyncMock()
        mock_retriever.save_file_stream = AsyncMock(side_effect=_consume_stream)
        file_manager._retriever = mock_retriever

        # Act
        with patch(
            "syntara.files.file_manager.validators.validate_single_file",
            new_callable=AsyncMock,
            return_value=(b"", "application/pdf"),
        ):
            mock_file = Mock(filename="test.pdf")
            mock_file.read = AsyncMock(side_effect=[file_content, b""])
            await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

        # Assert - verify audit event was emitted
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "files_uploaded"
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.files.file_manager"
        assert "1 files uploaded and stored for conversion" in event.event_message
        assert event.resource_urn is None  # Bulk operation
        assert event.resource_name is None

        # Verify structured data
        assert event.structured_data.file_count == 1  # type: ignore[attr-defined]
        assert event.structured_data.total_size_bytes == len(file_content)  # type: ignore[attr-defined]
        assert len(event.structured_data.file_details) == 1  # type: ignore[attr-defined]
        file_detail = event.structured_data.file_details[0]  # type: ignore[attr-defined]
        assert file_detail["filename"] == "test.pdf"
        assert file_detail["mime_type"] == "application/pdf"
        assert file_detail["size_bytes"] == len(file_content)
        assert "file_id" in file_detail

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_validate_and_save_files_multiple_files_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
    ) -> None:
        """Uploading multiple files should emit event with all file details."""

        # Arrange
        async def _consume_stream(stream: AsyncGenerator[bytes], path: str) -> tuple[str, int]:
            total = 0
            async for chunk in stream:
                total += len(chunk)
            return "orchestrator-uuid-test.pdf", total

        mock_files = []
        for i in range(3):
            mf = Mock(filename=f"test{i}.txt")
            mf.read = AsyncMock(side_effect=[f"File {i} content".encode(), b""])
            mock_files.append(mf)

        file_manager = FileManager()
        mock_retriever = AsyncMock()
        mock_retriever.save_file_stream = AsyncMock(side_effect=_consume_stream)
        file_manager._retriever = mock_retriever

        # Act
        with patch(
            "syntara.files.file_manager.validators.validate_single_file",
            new_callable=AsyncMock,
            side_effect=[(b"", "text/plain")] * 3,
        ):
            await file_manager.validate_and_save_files(cast("list[UploadFile]", mock_files), project_id=uuid4())

        # Assert
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "files_uploaded"
        assert event.event_severity == EventSeverity.INFO
        assert "3 files uploaded" in event.event_message
        assert event.structured_data.file_count == 3  # type: ignore[attr-defined]
        assert len(event.structured_data.file_details) == 3  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_validate_and_save_files_validation_error_emits_error_event(
        self,
        mock_do_emit: AsyncMock,
    ) -> None:
        """File validation error should emit error audit event before raising."""
        # Arrange
        mock_file = Mock()
        mock_file.filename = "bad.exe"

        file_manager = FileManager()
        mock_retriever = AsyncMock()
        file_manager._retriever = mock_retriever

        # Act & Assert
        with (
            patch(
                "syntara.files.file_manager.validators.validate_single_file",
                new_callable=AsyncMock,
                side_effect=FileValidationError("Unsupported MIME type"),
            ),
            pytest.raises(FileValidationError),
        ):
            await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

        # Verify error audit event was emitted
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "files_uploaded"
        assert event.event_severity == EventSeverity.ERROR
        assert event.event_status == EventStatus.ERROR
        assert event.event_message == "File upload failed"
        assert event.structured_data.error_type == "FileValidationError"
        assert event.structured_data.file_count == 1  # type: ignore[attr-defined]
        assert len(event.structured_data.file_details) == 1  # type: ignore[attr-defined]
        assert event.structured_data.file_details[0]["filename"] == "bad.exe"  # type: ignore[attr-defined]
        assert "Operational Logs" in str(event.structured_data.error_message)


class TestDocumentConversionServiceAuditEvents:
    """Tests for audit event emission from DocumentConversionService.convert_file()."""

    @pytest.fixture(autouse=True)
    def _mock_conversion_config(self) -> Generator[MagicMock]:
        """Patch ConversionConfig.from_settings so convert_file() doesn't hit SettingsCache."""
        mock_config = MagicMock()
        mock_config.overwrite_existing = True
        mock_config.timeout_seconds = 30
        mock_config.temp_dir = "/tmp/nexus-test"  # noqa: S108
        with patch(
            "syntara.files.document_conversion.services.document_conversion_service.ConversionConfig.from_settings",
            return_value=mock_config,
        ):
            yield mock_config

    def setup_method(self) -> None:
        """Register files audit handlers before each test."""
        from syntara.files.audit.file_converted import (
            FileConvertedEvent,
            FileConvertedHandler,
        )

        AuditEventDispatcher.register({FileConvertedEvent: FileConvertedHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_convert_file_success_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
    ) -> None:
        """Successful file conversion should emit FileConvertedEvent with SUCCESS state."""
        # Arrange
        file_id = uuid4()
        file_metadata = FileMetadata(
            id=file_id,
            filename="document.pdf",
            mime_type="application/pdf",
            size_bytes=2048,
            file_path="path/to/file.pdf",
            status=FileStatus.PENDING_CONVERSION,
        )

        mock_file_manager = Mock()
        mock_converter_registry = Mock()
        mock_converter = Mock()
        mock_retriever = AsyncMock()

        mock_file_manager.get_retriever.return_value = mock_retriever
        mock_retriever.load_file.return_value = b"PDF content"
        mock_converter_registry.get_converter.return_value = mock_converter
        mock_converter.convert_with_timeout = AsyncMock(
            return_value=ConversionResult.success_result(
                converted_content="# Converted markdown",
                conversion_time_ms=150,
            )
        )

        mock_retriever.save_file.return_value = "path/to/converted.md"

        service = DocumentConversionService(
            file_manager_factory=lambda: mock_file_manager,
            converter_registry_factory=lambda: mock_converter_registry,
        )
        status_updater = AsyncMock()

        # Act
        result = await service.convert_file(file_metadata, status_updater)

        # Assert
        assert result == ConversionState.SUCCESS
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "file_converted"
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.event_message == "File converted."
        assert event.source_component == "syntara.files.document_conversion"
        assert event.resource_urn == f"urn:syntara:file:{file_id}"
        assert event.resource_name == "document.pdf"

        # Verify structured data
        assert event.structured_data.file_id == str(file_id)  # type: ignore[attr-defined]
        assert event.structured_data.mime_type == "application/pdf"  # type: ignore[attr-defined]
        assert event.structured_data.size_bytes == 2048  # type: ignore[attr-defined]
        assert event.structured_data.conversion_state == ConversionStateAudit.SUCCESS  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_convert_file_failed_emits_error_audit_event(
        self,
        mock_do_emit: AsyncMock,
    ) -> None:
        """Failed file conversion should emit FileConvertedEvent with FAILED state."""
        # Arrange
        file_id = uuid4()
        file_metadata = FileMetadata(
            id=file_id,
            filename="broken.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            file_path="path/to/broken.pdf",
            status=FileStatus.PENDING_CONVERSION,
        )

        mock_file_manager = Mock()
        mock_converter_registry = Mock()
        mock_converter = Mock()
        mock_retriever = AsyncMock()

        mock_file_manager.get_retriever.return_value = mock_retriever
        mock_retriever.load_file.return_value = b"Broken PDF"
        mock_converter_registry.get_converter.return_value = mock_converter
        mock_converter.convert_with_timeout = AsyncMock(
            return_value=ConversionResult.failure_result(
                error_message="PDF parsing failed",
                error_type="PDFParseError",
                conversion_time_ms=50,
            )
        )

        service = DocumentConversionService(
            file_manager_factory=lambda: mock_file_manager,
            converter_registry_factory=lambda: mock_converter_registry,
        )
        status_updater = AsyncMock()

        # Act
        result = await service.convert_file(file_metadata, status_updater)

        # Assert
        assert result == ConversionState.FAILED
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "file_converted"
        assert event.event_severity == EventSeverity.ERROR
        assert event.event_status == EventStatus.ERROR
        assert event.event_message == "File conversion failed."
        assert event.source_component == "syntara.files.document_conversion"
        assert event.resource_urn == f"urn:syntara:file:{file_id}"
        assert event.resource_name == "broken.pdf"

        assert event.structured_data.conversion_state == ConversionStateAudit.FAILED  # type: ignore[attr-defined]
        assert event.structured_data.error_type == "ConversionFailureError"

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_convert_file_skipped_emits_warning_audit_event(
        self,
        mock_do_emit: AsyncMock,
    ) -> None:
        """Skipped file conversion should emit FileConvertedEvent with SKIPPED state."""
        # Arrange - file not in PENDING_CONVERSION state
        file_id = uuid4()
        file_metadata = FileMetadata(
            id=file_id,
            filename="already_converted.txt",
            mime_type="text/plain",
            size_bytes=512,
            file_path="path/to/file.txt",
            status=FileStatus.CONVERTED,  # Already converted
        )

        service = DocumentConversionService()
        status_updater = AsyncMock()

        # Act
        result = await service.convert_file(file_metadata, status_updater)

        # Assert
        assert result == ConversionState.SKIPPED
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "file_converted"
        assert event.event_severity == EventSeverity.WARNING
        assert event.event_status == EventStatus.SUCCESS
        assert event.event_message == "File conversion skipped."
        assert event.source_component == "syntara.files.document_conversion"
        assert event.resource_urn == f"urn:syntara:file:{file_id}"
        assert event.resource_name == "already_converted.txt"

        assert event.structured_data.conversion_state == ConversionStateAudit.SKIPPED  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_convert_file_missing_converter_emits_error_audit_event(
        self,
        mock_do_emit: AsyncMock,
    ) -> None:
        """Missing converter should emit error audit event."""
        # Arrange
        file_id = uuid4()
        file_metadata = FileMetadata(
            id=file_id,
            filename="unsupported.xyz",
            mime_type="application/x-unknown",
            size_bytes=1024,
            file_path="path/to/file.xyz",
            status=FileStatus.PENDING_CONVERSION,
        )

        mock_file_manager = Mock()
        mock_converter_registry = Mock()
        mock_retriever = AsyncMock()

        mock_file_manager.get_retriever.return_value = mock_retriever
        mock_retriever.load_file.return_value = b"Unknown content"
        mock_converter_registry.get_converter.return_value = None  # No converter

        service = DocumentConversionService(
            file_manager_factory=lambda: mock_file_manager,
            converter_registry_factory=lambda: mock_converter_registry,
        )
        status_updater = AsyncMock()

        # Act
        result = await service.convert_file(file_metadata, status_updater)

        # Assert
        assert result == ConversionState.FAILED
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_severity == EventSeverity.ERROR
        assert event.event_status == EventStatus.ERROR
        assert event.structured_data.conversion_state == ConversionStateAudit.FAILED  # type: ignore[attr-defined]
        assert event.structured_data.error_type == "UnsupportedFormatError"
