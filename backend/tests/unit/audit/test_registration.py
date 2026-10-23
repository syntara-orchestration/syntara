"""Unit tests for audit handler package registration."""

from __future__ import annotations

import syntara.telemetry.handlers
import syntara.workflows.audit
from syntara.audit.discovery import discover_handlers
from syntara.audit.registration import _handler_packages
from syntara.forms.audit.form_prompt import (
    FormPromptCreatedEvent,
    FormPromptExpiredEvent,
    FormPromptSubmittedEvent,
)
from syntara.invocations.audit.invocation_cancelled import InvocationCancelledEvent
from syntara.invocations.audit.invocation_created import InvocationCreatedEvent
from syntara.telemetry.handlers.form_trigger_submitted import FormTriggerSubmittedTelemetryHandler
from syntara.tool_manager.audit.tool_bulk_update import ToolBulkUpdateEvent
from syntara.tool_manager.audit.tool_update import ToolUpdateEvent
from syntara.workflows.audit.form_trigger import FormTriggerSubmittedEvent, FormTriggerSubmittedHandler


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

    def test_form_prompt_lifecycle_events_are_discoverable(self) -> None:
        event_types = {event_type for pkg in _handler_packages() for event_type in discover_handlers(pkg)}

        assert FormPromptCreatedEvent in event_types
        assert FormPromptSubmittedEvent in event_types
        assert FormPromptExpiredEvent in event_types

    def test_form_trigger_event_has_audit_and_telemetry_handlers(self) -> None:
        packages = {pkg.__name__: pkg for pkg in _handler_packages()}
        assert "syntara.workflows.audit" in packages
        assert "syntara.telemetry.handlers" in packages

        audit_handlers = discover_handlers(syntara.workflows.audit)
        telemetry_handlers = discover_handlers(syntara.telemetry.handlers)

        assert isinstance(audit_handlers[FormTriggerSubmittedEvent], FormTriggerSubmittedHandler)
        assert isinstance(telemetry_handlers[FormTriggerSubmittedEvent], FormTriggerSubmittedTelemetryHandler)
