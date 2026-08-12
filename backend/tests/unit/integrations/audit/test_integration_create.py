"""Unit tests for IntegrationCreateEvent and handler."""

from uuid import uuid4

import pytest

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.integrations.audit.integration_create import (
    IntegrationCreateEvent,
    IntegrationCreateHandler,
)
from syntara.integrations.models.integration import IntegrationStatus


class TestIntegrationCreateHandler:
    """Tests for IntegrationCreateHandler."""

    def _make_event(self, **overrides: object) -> IntegrationCreateEvent:
        defaults: dict[str, object] = {
            "integration_id": uuid4(),
            "integration_name": "GitHub MCP",
            "integration_type": "mcp_server",
            "description": "GitHub integration via MCP",
            "initial_status": IntegrationStatus.UNKNOWN,
        }
        defaults.update(overrides)
        return IntegrationCreateEvent(**defaults)  # type: ignore[arg-type]

    def test_success_event(self) -> None:
        """Should produce INFO SYSTEM_OPERATION event for successful creation."""
        handler = IntegrationCreateHandler()
        event = self._make_event()

        audit_event = handler.handle(event)

        assert audit_event.event_action == "integration_created"
        assert audit_event.event_category == EventCategory.SYSTEM_OPERATION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.source_component == "syntara.integrations.integration"
        assert audit_event.event_message == "Integration created: GitHub MCP"

    def test_error_event(self) -> None:
        """Should produce ERROR event when error_type is set."""
        handler = IntegrationCreateHandler()
        event = self._make_event(error_type="IntegrityError")

        audit_event = handler.handle(event)

        assert audit_event.event_severity == EventSeverity.ERROR
        assert audit_event.event_status == EventStatus.ERROR
        assert "failed" in audit_event.event_message
        assert audit_event.structured_data.error_type == "IntegrityError"

    def test_resource_fields(self) -> None:
        """Should set resource URN and name correctly."""
        handler = IntegrationCreateHandler()
        integration_id = uuid4()
        event = self._make_event(integration_id=integration_id, integration_name="Test Integration")

        audit_event = handler.handle(event)

        assert audit_event.resource_urn == f"urn:syntara:integration:{integration_id}"
        assert audit_event.resource_name == "Test Integration"

    def test_structured_data_fields(self) -> None:
        """Should include all relevant fields in structured data."""
        handler = IntegrationCreateHandler()
        event = self._make_event(
            integration_name="Slack MCP",
            integration_type="mcp_server",
            description="Slack integration",
            initial_status=IntegrationStatus.AVAILABLE,
        )

        audit_event = handler.handle(event)
        data = audit_event.structured_data

        assert data.data_type == "integration-create-context"
        assert data.integration_name == "Slack MCP"  # type: ignore[attr-defined]
        assert data.integration_type == "mcp_server"  # type: ignore[attr-defined]
        assert data.description == "Slack integration"  # type: ignore[attr-defined]
        assert data.initial_status == "available"  # type: ignore[attr-defined]
        assert data.error_type is None

    def test_none_description(self) -> None:
        """Should handle None description gracefully."""
        handler = IntegrationCreateHandler()
        event = self._make_event(description=None)

        audit_event = handler.handle(event)

        assert audit_event.structured_data.description is None  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "status",
        [IntegrationStatus.UNKNOWN, IntegrationStatus.VALIDATING, IntegrationStatus.AVAILABLE, IntegrationStatus.ERROR],
    )
    def test_different_initial_statuses(self, status: IntegrationStatus) -> None:
        """Should handle different initial statuses."""
        handler = IntegrationCreateHandler()
        event = self._make_event(initial_status=status)

        audit_event = handler.handle(event)

        assert audit_event.structured_data.initial_status == status.value  # type: ignore[attr-defined]
