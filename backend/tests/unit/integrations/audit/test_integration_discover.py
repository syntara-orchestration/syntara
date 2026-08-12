"""Unit tests for IntegrationDiscoverEvent and handler."""

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.integrations.audit.integration_discover import (
    IntegrationDiscoverEvent,
    IntegrationDiscoverHandler,
)


class TestIntegrationDiscoverHandler:
    """Tests for IntegrationDiscoverHandler."""

    def _make_event(self, **overrides: object) -> IntegrationDiscoverEvent:
        defaults: dict[str, object] = {
            "integration_type": "mcp_server",
            "tools_found_count": 5,
            "models_found_count": 0,
            "error_type": None,
        }
        defaults.update(overrides)
        return IntegrationDiscoverEvent(**defaults)  # type: ignore[arg-type]

    def test_success_event(self) -> None:
        """Should produce INFO event for successful discovery."""
        handler = IntegrationDiscoverHandler()
        event = self._make_event()

        audit_event = handler.handle(event)

        assert audit_event.event_action == "integration_discovered"
        assert audit_event.event_category == EventCategory.SYSTEM_OPERATION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.source_component == "syntara.integrations.integration"
        assert "successful" in audit_event.event_message
        assert "mcp_server" in audit_event.event_message

    def test_failure_event(self) -> None:
        """Should produce WARNING ERROR event for discovery failure."""
        handler = IntegrationDiscoverHandler()
        event = self._make_event(error_type="DiscoverFailed")

        audit_event = handler.handle(event)

        assert audit_event.event_severity == EventSeverity.WARNING
        assert audit_event.event_status == EventStatus.ERROR
        assert "failed" in audit_event.event_message
        assert audit_event.structured_data.error_type == "DiscoverFailed"
        assert audit_event.structured_data.error_message == "Look at the Operational Logs for full diagnosis"

    def test_no_resource_urn(self) -> None:
        """Discover has no saved integration ID so resource URN should be absent."""
        handler = IntegrationDiscoverHandler()
        event = self._make_event()

        audit_event = handler.handle(event)

        assert audit_event.resource_urn is None
        assert audit_event.resource_name is None

    def test_structured_data_fields(self) -> None:
        """Should include integration type and resource counts in structured data."""
        handler = IntegrationDiscoverHandler()
        event = self._make_event(
            integration_type="mcp_server",
            tools_found_count=3,
            models_found_count=2,
        )

        audit_event = handler.handle(event)
        data = audit_event.structured_data

        assert data.data_type == "integration-discover-context"
        assert data.integration_type == "mcp_server"  # type: ignore[attr-defined]
        assert data.tools_found_count == 3  # type: ignore[attr-defined]
        assert data.models_found_count == 2  # type: ignore[attr-defined]
        assert data.error_type is None
        assert data.error_message is None

    def test_zero_resources_found(self) -> None:
        """Should handle zero resources found gracefully."""
        handler = IntegrationDiscoverHandler()
        event = self._make_event(tools_found_count=0, models_found_count=0)

        audit_event = handler.handle(event)

        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.structured_data.tools_found_count == 0  # type: ignore[attr-defined]
        assert audit_event.structured_data.models_found_count == 0  # type: ignore[attr-defined]
