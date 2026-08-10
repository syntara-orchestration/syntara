"""FileDownloadedEvent and handler for file download operations."""

from dataclasses import dataclass, field
from uuid import UUID

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData


@dataclass
class FileDownloadedEvent:
    """Domain event emitted when a file is downloaded.

    Captures file metadata and storage backend used for retrieval.
    """

    file_id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    storage_backend: str
    error_type: str | None = field(default=None)


class FileDownloadedHandler(AuditEventHandler[FileDownloadedEvent]):
    """Maps a FileDownloadedEvent to a normalized AuditEvent."""

    def handle(self, event: FileDownloadedEvent) -> AuditEvent:
        """Convert FileDownloadedEvent to AuditEvent."""
        is_error = event.error_type is not None

        if is_error:
            severity = EventSeverity.WARNING
            event_status = EventStatus.ERROR
            message = f"File download failed: {event.filename}"
        else:
            severity = EventSeverity.INFO
            event_status = EventStatus.SUCCESS
            message = f"File downloaded: {event.filename} ({event.size_bytes} bytes via {event.storage_backend})"

        data = AuditContextData(
            data_type="file-downloaded-context",
            error_type=event.error_type,
            mime_type=event.mime_type,
            size_bytes=event.size_bytes,
            storage_backend=event.storage_backend,
        )

        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_severity=severity,
            event_status=event_status,
            event_action="file_downloaded",
            event_message=message,
            source_component="syntara.files.router",
            structured_data=data,
            resource_urn=f"urn:syntara:file:{event.file_id}",
            resource_name=event.filename,
        )
