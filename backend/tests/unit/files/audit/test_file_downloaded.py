"""Unit tests for FileDownloadedEvent audit handler."""

from uuid import uuid4

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.files.audit.file_downloaded import FileDownloadedEvent, FileDownloadedHandler


class TestFileDownloadedHandler:
    """Test FileDownloadedHandler maps events to AuditEvent correctly."""

    def test_success_produces_info_user_action(self) -> None:
        """Test that successful download produces INFO USER_ACTION."""
        file_id = uuid4()
        event = FileDownloadedEvent(
            file_id=file_id,
            filename="report.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            storage_backend="s3",
        )

        handler = FileDownloadedHandler()
        audit_event = handler.handle(event)

        assert audit_event.event_category == EventCategory.USER_ACTION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.event_action == "file_downloaded"
        assert "report.pdf" in audit_event.event_message
        assert audit_event.resource_urn == f"urn:syntara:file:{file_id}"

    def test_error_produces_warning(self) -> None:
        """Test that failed download produces WARNING with error_type."""
        event = FileDownloadedEvent(
            file_id=uuid4(),
            filename="missing.pdf",
            mime_type="application/pdf",
            size_bytes=512,
            storage_backend="s3",
            error_type="FileContentNotFoundError",
        )

        handler = FileDownloadedHandler()
        audit_event = handler.handle(event)

        assert audit_event.event_severity == EventSeverity.WARNING
        assert audit_event.event_status == EventStatus.ERROR
        assert "missing.pdf" in audit_event.event_message
