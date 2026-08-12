"""Unit tests for FileIntegrityFailedEvent audit handler."""

from uuid import uuid4

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.files.audit.file_integrity_failed import (
    FileIntegrityFailedEvent,
    FileIntegrityFailedHandler,
)


class TestFileIntegrityFailedHandler:
    """Test FileIntegrityFailedHandler maps events to AuditEvent correctly."""

    def test_produces_critical_security_event(self) -> None:
        """Test that integrity failure produces a CRITICAL SECURITY_EVENT."""
        file_id = uuid4()
        event = FileIntegrityFailedEvent(
            file_id=file_id,
            filename="tampered.pdf",
            storage_backend="s3",
            expected_hash="a" * 64,
            actual_hash="b" * 64,
        )

        handler = FileIntegrityFailedHandler()
        audit_event = handler.handle(event)

        assert audit_event is not None
        assert audit_event.event_category == EventCategory.SECURITY_EVENT
        assert audit_event.event_severity == EventSeverity.CRITICAL
        assert audit_event.event_status == EventStatus.ERROR
        assert audit_event.event_action == "file_integrity_failed"
        assert "tampered.pdf" in audit_event.event_message
        assert audit_event.resource_urn == f"urn:syntara:file:{file_id}"
        assert audit_event.resource_name == "tampered.pdf"
        assert audit_event.source_component == "syntara.files.file_manager"

    def test_structured_data_contains_hash_details(self) -> None:
        """Test that structured_data includes expected and actual hashes."""
        event = FileIntegrityFailedEvent(
            file_id=uuid4(),
            filename="corrupted.bin",
            storage_backend="s3",
            expected_hash="expected123",
            actual_hash="actual456",
        )

        handler = FileIntegrityFailedHandler()
        audit_event = handler.handle(event)

        assert audit_event.structured_data.data_type == "file-integrity-failed"
        assert audit_event.structured_data.model_extra is not None
        assert audit_event.structured_data.model_extra["storage_backend"] == "s3"
        assert audit_event.structured_data.model_extra["expected_hash"] == "expected123"
        assert audit_event.structured_data.model_extra["actual_hash"] == "actual456"
