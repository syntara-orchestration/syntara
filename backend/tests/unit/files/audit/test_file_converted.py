"""Unit tests for FileConvertedEvent and FileConvertedHandler."""

from uuid import UUID, uuid4

import pytest

from syntara.audit.models.audit_event import EventSeverity, EventStatus
from syntara.files.audit.file_converted import (
    ConversionStateAudit,
    FileConvertedEvent,
    FileConvertedHandler,
)


class TestFileConvertedHandler:
    """Test FileConvertedHandler event-to-AuditEvent mapping."""

    @pytest.fixture
    def handler(self) -> FileConvertedHandler:
        """Create a FileConvertedHandler instance."""
        return FileConvertedHandler()

    @pytest.fixture
    def test_file_id(self) -> UUID:
        """Generate a test file UUID."""
        return uuid4()

    def test_success_event_mapping(self, handler: FileConvertedHandler, test_file_id: UUID) -> None:
        """SUCCESS conversion should create INFO AuditEvent."""
        event = FileConvertedEvent(
            file_id=test_file_id,
            filename="document.pdf",
            mime_type="application/pdf",
            size_bytes=2048,
            conversion_state=ConversionStateAudit.SUCCESS,
            conversion_time_ms=150,
        )

        audit_event = handler.handle(event)

        assert audit_event.event_action == "file_converted"
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.event_message == "File converted."
        assert audit_event.source_component == "syntara.files.document_conversion"
        assert audit_event.resource_urn == f"urn:syntara:file:{test_file_id}"
        assert audit_event.resource_name == "document.pdf"

    def test_failed_event_mapping(self, handler: FileConvertedHandler, test_file_id: UUID) -> None:
        """FAILED conversion should create ERROR AuditEvent."""
        event = FileConvertedEvent(
            file_id=test_file_id,
            filename="broken.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            conversion_state=ConversionStateAudit.FAILED,
            error_type="ConversionFailureError",
        )

        audit_event = handler.handle(event)

        assert audit_event.event_action == "file_converted"
        assert audit_event.event_severity == EventSeverity.ERROR
        assert audit_event.event_status == EventStatus.ERROR
        assert audit_event.event_message == "File conversion failed."
        assert audit_event.structured_data.error_type == "ConversionFailureError"
        assert "Operational Logs" in str(audit_event.structured_data.error_message)
        assert audit_event.resource_urn == f"urn:syntara:file:{test_file_id}"
        assert audit_event.resource_name == "broken.pdf"

    def test_skipped_event_mapping(self, handler: FileConvertedHandler, test_file_id: UUID) -> None:
        """SKIPPED conversion should create WARNING AuditEvent with SUCCESS status."""
        event = FileConvertedEvent(
            file_id=test_file_id,
            filename="already_converted.txt",
            mime_type="text/plain",
            size_bytes=512,
            conversion_state=ConversionStateAudit.SKIPPED,
        )

        audit_event = handler.handle(event)

        assert audit_event.event_action == "file_converted"
        assert audit_event.event_severity == EventSeverity.WARNING
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.event_message == "File conversion skipped."
        assert audit_event.resource_urn == f"urn:syntara:file:{test_file_id}"
        assert audit_event.resource_name == "already_converted.txt"

    def test_resource_urn_format(self, handler: FileConvertedHandler, test_file_id: UUID) -> None:
        """Resource URN should follow RFC 8141 format."""
        event = FileConvertedEvent(
            file_id=test_file_id,
            filename="test.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            conversion_state=ConversionStateAudit.SUCCESS,
        )

        audit_event = handler.handle(event)

        assert audit_event.resource_urn == f"urn:syntara:file:{test_file_id}"
        assert audit_event.resource_urn.startswith("urn:syntara:file:")

    def test_structured_data_includes_conversion_details(
        self, handler: FileConvertedHandler, test_file_id: UUID
    ) -> None:
        """Structured data should include all conversion metadata."""
        event = FileConvertedEvent(
            file_id=test_file_id,
            filename="report.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=4096,
            conversion_state=ConversionStateAudit.SUCCESS,
            conversion_time_ms=250,
        )

        audit_event = handler.handle(event)

        assert audit_event.structured_data.data_type == "file-converted-context"
        assert audit_event.structured_data.file_id == str(test_file_id)  # type: ignore[attr-defined]
        assert audit_event.structured_data.mime_type == event.mime_type  # type: ignore[attr-defined]
        assert audit_event.structured_data.size_bytes == 4096  # type: ignore[attr-defined]
        assert audit_event.structured_data.conversion_state == ConversionStateAudit.SUCCESS  # type: ignore[attr-defined]
        assert audit_event.structured_data.conversion_time_ms == 250  # type: ignore[attr-defined]
