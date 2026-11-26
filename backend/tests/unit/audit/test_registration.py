"""Unit tests for audit handler package registration."""

from __future__ import annotations

from syntara.audit.discovery import discover_handlers
from syntara.audit.registration import _handler_packages
from syntara.eventstreams import audit as eventstreams_audit
from syntara.eventstreams.audit.record_rejection import EventRecordRejectedEvent, EventRecordRejectedHandler
from syntara.invocations.audit.invocation_cancelled import InvocationCancelledEvent
from syntara.invocations.audit.invocation_created import InvocationCreatedEvent
from syntara.tool_manager.audit.tool_bulk_update import ToolBulkUpdateEvent
from syntara.tool_manager.audit.tool_update import ToolUpdateEvent


class TestHandlerPackagesRegistration:
    """Tests for packages registered with the audit dispatcher."""

    def test_tool_manager_and_invocations_packages_are_registered(self) -> None:
        package_names = {pkg.__name__ for pkg in _handler_packages()}
        assert "syntara.tool_manager.audit" in package_names
        assert "syntara.invocations.audit" in package_names

    def test_tool_and_invocation_events_are_discoverable(self) -> None:
        event_types = {event_type for pkg in _handler_packages() for event_type in discover_handlers(pkg)}
        assert ToolUpdateEvent in event_types
        assert ToolBulkUpdateEvent in event_types
        assert InvocationCreatedEvent in event_types
        assert InvocationCancelledEvent in event_types

    def test_eventstream_record_rejection_handler_is_registered_and_discoverable(self) -> None:
        assert eventstreams_audit in _handler_packages()

        handlers = discover_handlers(eventstreams_audit)

        assert isinstance(handlers[EventRecordRejectedEvent], EventRecordRejectedHandler)
