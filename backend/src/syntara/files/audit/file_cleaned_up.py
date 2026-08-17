"""Audit event and handler for file lifecycle cleanup operations."""

from __future__ import annotations

from dataclasses import dataclass

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData


@dataclass
class FileCleanedUpEvent:
    """Domain event emitted when files are cleaned up by the lifecycle worker."""

    files_deleted: int
    multipart_uploads_aborted: int


class FileCleanedUpHandler(AuditEventHandler[FileCleanedUpEvent]):
    """Maps a FileCleanedUpEvent to a normalized AuditEvent."""

    def handle(self, event: FileCleanedUpEvent) -> AuditEvent:
        """Map a file cleanup event to a normalized audit event."""
        message = (
            f"File cleanup completed: {event.files_deleted} files deleted, "
            f"{event.multipart_uploads_aborted} stale multipart uploads aborted"
        )

        data = AuditContextData(
            data_type="file-cleaned-up-context",
            files_deleted=event.files_deleted,
            multipart_uploads_aborted=event.multipart_uploads_aborted,
        )

        return AuditEvent(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="file_cleaned_up",
            event_message=message,
            source_component="syntara.files.workers.file_cleanup",
            structured_data=data,
        )
