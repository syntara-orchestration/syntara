"""Unit tests for AuditEventHandler ABC."""

from dataclasses import dataclass

import pytest

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory
from syntara.audit.models.structured_data import AuditContextData


@dataclass
class _StubEvent:
    """Minimal domain event for testing."""

    name: str


class _StubHandler(AuditEventHandler["_StubEvent"]):
    """Concrete handler for testing the ABC contract."""

    def handle(self, event: "_StubEvent") -> AuditEvent:
        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="stub",
            event_message=event.name,
            source_component="test",
            structured_data=AuditContextData(data_type="test"),
        )


class TestAuditEventHandler:
    """Tests for AuditEventHandler ABC."""

    def test_concrete_subclass_can_be_instantiated(self) -> None:
        """A concrete subclass implementing handle() can be instantiated."""
        handler = _StubHandler()
        assert isinstance(handler, AuditEventHandler)

    def test_handle_returns_audit_event(self) -> None:
        """handle() maps a domain event to an AuditEvent."""
        handler = _StubHandler()
        event = _StubEvent(name="test-event")
        result = handler.handle(event)
        assert isinstance(result, AuditEvent)
        assert result.event_action == "stub"
        assert result.event_message == "test-event"

    def test_abstract_class_cannot_be_instantiated(self) -> None:
        """AuditEventHandler itself cannot be instantiated."""
        with pytest.raises(TypeError):
            AuditEventHandler()  # type: ignore[abstract]
