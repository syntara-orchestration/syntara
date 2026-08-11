"""FileIntegrityFailedEvent and handler for integrity verification failures."""

from dataclasses import dataclass
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
class FileIntegrityFailedEvent:
    """Domain event emitted when a file's content hash does not match the stored hash.

    This is a security-relevant event indicating possible data corruption
    or tampering in the storage backend.
    """

    file_id: UUID
    filename: str
    storage_backend: str
    expected_hash: str
    actual_hash: str


class FileIntegrityFailedHandler(AuditEventHandler[FileIntegrityFailedEvent]):
    """Maps a FileIntegrityFailedEvent to a normalized AuditEvent.

    Always CRITICAL severity — hash mismatch indicates corruption or tampering.
    """

    def handle(self, event: FileIntegrityFailedEvent) -> AuditEvent:
        """Convert FileIntegrityFailedEvent to AuditEvent."""
        data = AuditContextData(
            data_type="file-integrity-failed",
            storage_backend=event.storage_backend,
            expected_hash=event.expected_hash,
            actual_hash=event.actual_hash,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.CRITICAL,
            event_status=EventStatus.ERROR,
            event_action="file_integrity_failed",
            event_message=f"File integrity check failed: content hash mismatch for {event.filename}",
            source_component="syntara.files.file_manager",
            structured_data=data,
            resource_urn=f"urn:syntara:file:{event.file_id}",
            resource_name=event.filename,
        )
