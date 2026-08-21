"""FileDeletedEvent and handler for file deletion operations."""

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
class FileDeletedEvent:
    """Domain event emitted when a file is deleted via the API."""

    file_id: UUID
    filename: str
    project_id: UUID
    storage_backend: str
    error_type: str | None = field(default=None)


class FileDeletedHandler(AuditEventHandler[FileDeletedEvent]):
    """Maps a FileDeletedEvent to a normalized AuditEvent."""

    def handle(self, event: FileDeletedEvent) -> AuditEvent:
        """Convert FileDeletedEvent to AuditEvent."""
        is_error = event.error_type is not None

        if is_error:
            severity = EventSeverity.WARNING
            event_status = EventStatus.ERROR
            message = f"File delete failed: {event.filename}"
        else:
            severity = EventSeverity.INFO
            event_status = EventStatus.SUCCESS
            message = f"File deleted: {event.filename} (via {event.storage_backend})"

        data = AuditContextData(
            data_type="file-deleted-context",
            error_type=event.error_type,
            storage_backend=event.storage_backend,
            project_id=str(event.project_id),
        )

        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_severity=severity,
            event_status=event_status,
            event_action="file_deleted",
            event_message=message,
            source_component="syntara.files.router",
            structured_data=data,
            resource_urn=f"urn:syntara:file:{event.file_id}",
            resource_name=event.filename,
        )
