"""FileConvertedEvent and handler for file conversion operations."""

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData


class ConversionStateAudit(StrEnum):
    """Conversion state for audit events."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class FileConvertedEvent:
    """Domain event emitted when a file conversion completes (success, failure, or skip).

    Captures the conversion outcome and relevant file metadata.
    """

    file_id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    conversion_state: ConversionStateAudit
    conversion_time_ms: int | None = field(default=None)
    error_type: str | None = field(default=None)


class FileConvertedHandler(AuditEventHandler[FileConvertedEvent]):
    """Maps a FileConvertedEvent to a normalized AuditEvent.

    - SUCCESS: severity=INFO, status=SUCCESS
    - FAILED: severity=ERROR, status=ERROR
    - SKIPPED: severity=WARNING, status=SUCCESS (not an error, but noteworthy)
    """

    def handle(self, event: FileConvertedEvent) -> AuditEvent:
        """Convert FileConvertedEvent to AuditEvent."""
        if event.conversion_state == ConversionStateAudit.SUCCESS:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            action = "file_converted"
            message = "File converted."
            error_message = None
        elif event.conversion_state == ConversionStateAudit.FAILED:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            action = "file_converted"
            message = "File conversion failed."
            error_message = "Look at the Operational Logs for full diagnosis"
        else:
            category = EventCategory.SYSTEM_OPERATION
            severity = EventSeverity.WARNING
            status = EventStatus.SUCCESS
            action = "file_converted"
            message = "File conversion skipped."
            error_message = None

        data = AuditContextData(
            data_type="file-converted-context",
            error_type=event.error_type,
            error_message=error_message,
            file_id=str(event.file_id),
            mime_type=event.mime_type,
            size_bytes=event.size_bytes,
            conversion_state=event.conversion_state,
            conversion_time_ms=event.conversion_time_ms,
        )

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            event_status=status,
            event_action=action,
            event_message=message,
            source_component="syntara.files.document_conversion",
            structured_data=data,
            resource_urn=f"urn:syntara:file:{event.file_id}",
            resource_name=event.filename,
        )
