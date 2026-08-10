"""Unit tests for AuditOutboxRecord model."""

from syntara.audit.outbox.models import AuditEventSource, AuditOutboxRecord
from syntara.core.models.base.base_resource import AuditLevel


class TestAuditEventSource:
    """Test AuditEventSource enum."""

    def test_enum_has_business_event_value(self) -> None:
        """Test BUSINESS_EVENT enum value."""
        assert AuditEventSource.BUSINESS_EVENT.value == "business_event"

    def test_enum_has_crud_event_value(self) -> None:
        """Test CRUD_EVENT enum value."""
        assert AuditEventSource.CRUD_EVENT.value == "crud_event"

    def test_enum_values_are_alphabetically_ordered(self) -> None:
        """Test that enum values are in alphabetical order (for PostgreSQL sorting)."""
        values = list(AuditEventSource)
        assert values == [AuditEventSource.BUSINESS_EVENT, AuditEventSource.CRUD_EVENT]

    def test_enum_is_str_enum(self) -> None:
        """Test that enum inherits from StrEnum for string serialization."""
        assert isinstance(AuditEventSource.BUSINESS_EVENT, str)
        assert isinstance(AuditEventSource.CRUD_EVENT, str)


class TestAuditOutboxRecordDefaults:
    """Test AuditOutboxRecord default values."""

    def test_default_event_source_is_business_event(self) -> None:
        """Test that event_source defaults to BUSINESS_EVENT when not specified."""
        record = AuditOutboxRecord(
            event_payload={"test": "data"},
        )

        assert record.event_source == AuditEventSource.BUSINESS_EVENT

    def test_event_source_can_be_set_to_crud_event(self) -> None:
        """Test that event_source can be explicitly set to CRUD_EVENT."""
        record = AuditOutboxRecord(
            event_payload={"test": "data"},
            event_source=AuditEventSource.CRUD_EVENT,
        )

        assert record.event_source == AuditEventSource.CRUD_EVENT

    def test_event_source_can_be_set_to_business_event(self) -> None:
        """Test that event_source can be explicitly set to BUSINESS_EVENT."""
        record = AuditOutboxRecord(
            event_payload={"test": "data"},
            event_source=AuditEventSource.BUSINESS_EVENT,
        )

        assert record.event_source == AuditEventSource.BUSINESS_EVENT


class TestAuditOutboxRecordTableConfig:
    """Test AuditOutboxRecord table configuration."""

    def test_tablename(self) -> None:
        """Test that the table name is audit_outbox."""
        assert AuditOutboxRecord.__tablename__ == "audit_outbox"

    def test_auditable_is_disabled(self) -> None:
        """Test that CRUD auditing is disabled to prevent recursion."""
        assert AuditOutboxRecord.__auditable__ == AuditLevel.NONE
