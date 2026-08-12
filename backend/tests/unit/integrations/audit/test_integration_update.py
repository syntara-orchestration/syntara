"""Unit tests for IntegrationUpdateEvent and handler."""

from uuid import uuid4

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.integrations.audit.integration_update import (
    IntegrationUpdateEvent,
    IntegrationUpdateHandler,
)


class TestIntegrationUpdateHandler:
    """Tests for IntegrationUpdateHandler."""

    def _make_event(self, **overrides: object) -> IntegrationUpdateEvent:
        defaults: dict[str, object] = {
            "integration_id": uuid4(),
            "integration_name": "GitHub MCP",
            "updated_fields": ["name", "description"],
            "integration_type": "mcp_server",
        }
        defaults.update(overrides)
        return IntegrationUpdateEvent(**defaults)  # type: ignore[arg-type]

    def test_success_event(self) -> None:
        """Should produce INFO SYSTEM_OPERATION event for successful update."""
        handler = IntegrationUpdateHandler()
        event = self._make_event()

        audit_event = handler.handle(event)

        assert audit_event.event_action == "integration_updated"
        assert audit_event.event_category == EventCategory.SYSTEM_OPERATION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.source_component == "syntara.integrations.integration"
        assert audit_event.event_message == "Integration updated: GitHub MCP"

    def test_error_event(self) -> None:
        """Should produce ERROR event when error_type is set."""
        handler = IntegrationUpdateHandler()
        event = self._make_event(error_type="IntegrationNotFoundError")

        audit_event = handler.handle(event)

        assert audit_event.event_severity == EventSeverity.ERROR
        assert audit_event.event_status == EventStatus.ERROR
        assert "failed" in audit_event.event_message
        assert audit_event.structured_data.error_type == "IntegrationNotFoundError"

    def test_resource_fields(self) -> None:
        """Should set resource URN and name correctly."""
        handler = IntegrationUpdateHandler()
        integration_id = uuid4()
        event = self._make_event(integration_id=integration_id, integration_name="Test Integration")

        audit_event = handler.handle(event)

        assert audit_event.resource_urn == f"urn:syntara:integration:{integration_id}"
        assert audit_event.resource_name == "Test Integration"

    def test_structured_data_fields(self) -> None:
        """Should include all relevant fields in structured data."""
        handler = IntegrationUpdateHandler()
        event = self._make_event(
            integration_name="Slack MCP",
            updated_fields=["name", "configuration"],
            integration_type="mcp_server",
        )

        audit_event = handler.handle(event)
        data = audit_event.structured_data

        assert data.data_type == "integration-update-context"
        assert data.integration_name == "Slack MCP"  # type: ignore[attr-defined]
        assert data.updated_fields == ["name", "configuration"]  # type: ignore[attr-defined]
        assert data.integration_type == "mcp_server"  # type: ignore[attr-defined]
        assert data.error_type is None

    def test_empty_updated_fields(self) -> None:
        """Should handle empty updated_fields list."""
        handler = IntegrationUpdateHandler()
        event = self._make_event(updated_fields=[])

        audit_event = handler.handle(event)

        assert audit_event.structured_data.updated_fields == []  # type: ignore[attr-defined]

    def test_single_field_update(self) -> None:
        """Should handle single field update."""
        handler = IntegrationUpdateHandler()
        event = self._make_event(updated_fields=["description"])

        audit_event = handler.handle(event)

        assert audit_event.structured_data.updated_fields == ["description"]  # type: ignore[attr-defined]

    def test_none_integration_type(self) -> None:
        """Should handle None integration_type gracefully."""
        handler = IntegrationUpdateHandler()
        event = self._make_event(integration_type=None)

        audit_event = handler.handle(event)

        assert audit_event.structured_data.integration_type is None  # type: ignore[attr-defined]
