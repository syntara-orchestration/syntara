"""Unit tests for FileCleanedUpEvent audit handler."""

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.files.audit.file_cleaned_up import FileCleanedUpEvent, FileCleanedUpHandler


class TestFileCleanedUpHandler:
    """Tests for FileCleanedUpHandler audit event production."""

    def test_success_produces_info_system_operation(self) -> None:
        event = FileCleanedUpEvent(files_deleted=5, multipart_uploads_aborted=2)
        handler = FileCleanedUpHandler()
        audit_event = handler.handle(event)
        assert audit_event.event_category == EventCategory.SYSTEM_OPERATION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.event_action == "file_cleaned_up"
        assert "5 files deleted" in audit_event.event_message
        assert "2 stale multipart uploads aborted" in audit_event.event_message

    def test_zero_cleanup_still_success(self) -> None:
        event = FileCleanedUpEvent(files_deleted=0, multipart_uploads_aborted=0)
        handler = FileCleanedUpHandler()
        audit_event = handler.handle(event)
        assert audit_event.event_status == EventStatus.SUCCESS
