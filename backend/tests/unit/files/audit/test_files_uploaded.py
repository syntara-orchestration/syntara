"""Unit tests for FilesUploadedEvent and FilesUploadedHandler."""

from uuid import uuid4

import pytest

from syntara.audit.models.audit_event import EventSeverity, EventStatus
from syntara.files.audit.files_uploaded import FilesUploadedEvent, FilesUploadedHandler


class TestFilesUploadedHandler:
    """Test FilesUploadedHandler event-to-AuditEvent mapping."""

    @pytest.fixture
    def handler(self) -> FilesUploadedHandler:
        """Create a FilesUploadedHandler instance."""
        return FilesUploadedHandler()

    def test_success_event_mapping(self, handler: FilesUploadedHandler) -> None:
        """Successful file upload should create INFO AuditEvent with file details."""
        file_details = [
            {
                "file_id": str(uuid4()),
                "filename": "test1.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 1024,
            },
            {
                "file_id": str(uuid4()),
                "filename": "test2.docx",
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "size_bytes": 2048,
            },
        ]
        event = FilesUploadedEvent(
            file_count=2,
            total_size_bytes=3072,
            file_details=file_details,
        )

        audit_event = handler.handle(event)

        assert audit_event.event_action == "files_uploaded"
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert "2 files uploaded and stored for conversion" in audit_event.event_message
        assert "0.00 MB" in audit_event.event_message
        assert audit_event.source_component == "syntara.files.file_manager"
        assert audit_event.resource_urn is None  # Bulk operation
        assert audit_event.resource_name is None  # Bulk operation

    def test_error_event_mapping(self, handler: FilesUploadedHandler) -> None:
        """Failed file upload should create ERROR AuditEvent."""
        event = FilesUploadedEvent(
            file_count=0,
            total_size_bytes=0,
            file_details=[],
            error_type="FileValidationError",
        )

        audit_event = handler.handle(event)

        assert audit_event.event_action == "files_uploaded"
        assert audit_event.event_severity == EventSeverity.ERROR
        assert audit_event.event_status == EventStatus.ERROR
        assert audit_event.event_message == "File upload failed"
        assert audit_event.source_component == "syntara.files.file_manager"
        assert audit_event.structured_data.error_type == "FileValidationError"
        assert "Operational Logs" in str(audit_event.structured_data.error_message)

    def test_structured_data_includes_file_details(self, handler: FilesUploadedHandler) -> None:
        """Structured data should include all file_details."""
        file_details = [
            {
                "file_id": str(uuid4()),
                "filename": "doc.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 5000,
            }
        ]
        event = FilesUploadedEvent(
            file_count=1,
            total_size_bytes=5000,
            file_details=file_details,
        )

        audit_event = handler.handle(event)

        assert audit_event.structured_data.data_type == "files-uploaded-context"
        assert audit_event.structured_data.file_count == 1  # type: ignore[attr-defined]
        assert audit_event.structured_data.total_size_bytes == 5000  # type: ignore[attr-defined]
        assert audit_event.structured_data.file_details == file_details  # type: ignore[attr-defined]
        assert len(audit_event.structured_data.file_details) == 1  # type: ignore[attr-defined]
        assert audit_event.structured_data.file_details[0]["filename"] == "doc.pdf"  # type: ignore[attr-defined]

    def test_resource_urn_is_none_for_bulk_operation(self, handler: FilesUploadedHandler) -> None:
        """Bulk operations should not have resource_urn or resource_name."""
        event = FilesUploadedEvent(
            file_count=5,
            total_size_bytes=10000,
            file_details=[],
        )

        audit_event = handler.handle(event)

        assert audit_event.resource_urn is None
        assert audit_event.resource_name is None

    def test_size_formatting_in_message(self, handler: FilesUploadedHandler) -> None:
        """Message should format size in MB with 2 decimal places."""
        event = FilesUploadedEvent(
            file_count=1,
            total_size_bytes=1_572_864,  # 1.5 MB
            file_details=[],
        )

        audit_event = handler.handle(event)

        assert "1.50 MB" in audit_event.event_message
