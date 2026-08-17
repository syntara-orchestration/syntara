"""FilesUploadedEvent and handler for file upload operations."""

from dataclasses import dataclass, field
from typing import Any

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData


@dataclass
class FilesUploadedEvent:
    """Domain event emitted when files are uploaded and stored.

    Captures metadata about uploaded files including filename, MIME type, and size.
    This is a bulk operation event (multiple files uploaded in one request).
    """

    file_count: int
    total_size_bytes: int
    file_details: list[dict[str, Any]] = field(default_factory=list)
    error_type: str | None = field(default=None)


class FilesUploadedHandler(AuditEventHandler[FilesUploadedEvent]):
    """Maps a FilesUploadedEvent to a normalized AuditEvent.

    Success events include file count and total size in the message.
    Error events indicate upload failure with generic error message.
    This is a bulk operation, so resource_urn and resource_name are None.
    """

    def handle(self, event: FilesUploadedEvent) -> AuditEvent:
        """Convert FilesUploadedEvent to AuditEvent."""
        is_error = event.error_type is not None

        if is_error:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            action = "files_uploaded"
            message = "File upload failed"
            error_message = "Look at the Operational Logs for full diagnosis"
        else:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            action = "files_uploaded"
            total_mb = event.total_size_bytes / (1024 * 1024)
            message = f"{event.file_count} files uploaded and stored for conversion (total size: {total_mb:.2f} MB)"
            error_message = None

        data = AuditContextData(
            data_type="files-uploaded-context",
            error_type=event.error_type,
            error_message=error_message,
            file_count=event.file_count,
            total_size_bytes=event.total_size_bytes,
            file_details=event.file_details,
        )

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            event_status=status,
            event_action=action,
            event_message=message,
            source_component="syntara.files.file_manager",
            structured_data=data,
            resource_urn=None,  # Bulk operation
            resource_name=None,  # Bulk operation
        )
