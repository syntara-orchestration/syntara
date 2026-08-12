"""Unit tests for IntegrationDeleteEvent and handler."""

from uuid import uuid4

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.integrations.audit.integration_delete import (
    IntegrationDeleteEvent,
    IntegrationDeleteHandler,
)


class TestIntegrationDeleteHandler:
    """Tests for IntegrationDeleteHandler."""

    def _make_event(self, **overrides: object) -> IntegrationDeleteEvent:
        defaults: dict[str, object] = {
            "integration_id": uuid4(),
            "integration_name": "GitHub MCP",
            "tools_deleted": 5,
        }
        defaults.update(overrides)
        return IntegrationDeleteEvent(**defaults)  # type: ignore[arg-type]

    def test_success_event(self) -> None:
        """Should produce INFO SYSTEM_OPERATION event for successful deletion."""
        handler = IntegrationDeleteHandler()
        event = self._make_event()

        audit_event = handler.handle(event)

        assert audit_event.event_action == "integration_deleted"
        assert audit_event.event_category == EventCategory.SYSTEM_OPERATION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.source_component == "syntara.integrations.integration"
        assert audit_event.event_message == "Integration deleted: GitHub MCP"

    def test_error_event(self) -> None:
        """Should produce ERROR event when error_type is set."""
        handler = IntegrationDeleteHandler()
        event = self._make_event(error_type="IntegrationNotFoundError")

        audit_event = handler.handle(event)

        assert audit_event.event_severity == EventSeverity.ERROR
        assert audit_event.event_status == EventStatus.ERROR
        assert "failed" in audit_event.event_message
        assert audit_event.structured_data.error_type == "IntegrationNotFoundError"

    def test_resource_fields(self) -> None:
        """Should set resource URN and name correctly."""
        handler = IntegrationDeleteHandler()
        integration_id = uuid4()
        event = self._make_event(integration_id=integration_id, integration_name="Test Integration")

        audit_event = handler.handle(event)

        assert audit_event.resource_urn == f"urn:syntara:integration:{integration_id}"
        assert audit_event.resource_name == "Test Integration"

    def test_structured_data_fields(self) -> None:
        """Should include all relevant fields in structured data."""
        handler = IntegrationDeleteHandler()
        event = self._make_event(
            integration_name="Slack MCP",
            tools_deleted=12,
        )

        audit_event = handler.handle(event)
        data = audit_event.structured_data

        assert data.data_type == "integration-delete-context"
        assert data.integration_name == "Slack MCP"  # type: ignore[attr-defined]
        assert data.tools_deleted == 12  # type: ignore[attr-defined]
        assert data.error_type is None

    def test_zero_tools_deleted(self) -> None:
        """Should handle zero tools deleted gracefully."""
        handler = IntegrationDeleteHandler()
        event = self._make_event(tools_deleted=0)

        audit_event = handler.handle(event)

        assert audit_event.structured_data.tools_deleted == 0  # type: ignore[attr-defined]

    def test_single_tool_deleted(self) -> None:
        """Should handle single tool deletion."""
        handler = IntegrationDeleteHandler()
        event = self._make_event(tools_deleted=1)

        audit_event = handler.handle(event)

        assert audit_event.structured_data.tools_deleted == 1  # type: ignore[attr-defined]
