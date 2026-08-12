"""Unit tests for IntegrationRefreshEvent and handler."""

from uuid import uuid4

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.integrations.audit.integration_refresh import (
    IntegrationRefreshEvent,
    IntegrationRefreshHandler,
)
from syntara.integrations.models.integration import IntegrationRefreshStatus


class TestIntegrationRefreshHandler:
    """Tests for IntegrationRefreshHandler."""

    def _make_event(self, **overrides: object) -> IntegrationRefreshEvent:
        defaults: dict[str, object] = {
            "integration_id": uuid4(),
            "integration_name": "GitHub MCP",
            "integration_type": "mcp_server",
            "result_status": IntegrationRefreshStatus.AVAILABLE,
            "synced_count": 5,
            "updated_count": 1,
            "missing_count": 0,
            "error_type": None,
        }
        defaults.update(overrides)
        return IntegrationRefreshEvent(**defaults)  # type: ignore[arg-type]

    def test_success_event(self) -> None:
        """Should produce INFO event for successful refresh."""
        handler = IntegrationRefreshHandler()
        event = self._make_event()

        audit_event = handler.handle(event)

        assert audit_event.event_action == "integration_refreshed"
        assert audit_event.event_category == EventCategory.SYSTEM_OPERATION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.source_component == "syntara.integrations.integration"
        assert "GitHub MCP" in audit_event.event_message
        assert "successful" in audit_event.event_message

    def test_failure_event(self) -> None:
        """Should produce WARNING ERROR event for refresh failure."""
        handler = IntegrationRefreshHandler()
        event = self._make_event(
            error_type="DiscoverFailed",
            result_status=IntegrationRefreshStatus.ERROR,
            synced_count=0,
            updated_count=0,
            missing_count=0,
        )

        audit_event = handler.handle(event)

        assert audit_event.event_severity == EventSeverity.WARNING
        assert audit_event.event_status == EventStatus.ERROR
        assert "failed" in audit_event.event_message
        assert audit_event.structured_data.error_type == "DiscoverFailed"
        assert audit_event.structured_data.error_message == "Look at the Operational Logs for full diagnosis"

    def test_resource_fields(self) -> None:
        """Should set resource URN and name from integration ID."""
        handler = IntegrationRefreshHandler()
        integration_id = uuid4()
        event = self._make_event(integration_id=integration_id, integration_name="Test Integration")

        audit_event = handler.handle(event)

        assert audit_event.resource_urn == f"urn:syntara:integration:{integration_id}"
        assert audit_event.resource_name == "Test Integration"

    def test_structured_data_fields(self) -> None:
        """Should include tool counts and result status in structured data."""
        handler = IntegrationRefreshHandler()
        event = self._make_event(
            integration_name="Slack MCP",
            integration_type="mcp_server",
            result_status=IntegrationRefreshStatus.AVAILABLE,
            synced_count=10,
            updated_count=3,
            missing_count=2,
        )

        audit_event = handler.handle(event)
        data = audit_event.structured_data

        assert data.data_type == "integration-refresh-context"
        assert data.integration_name == "Slack MCP"  # type: ignore[attr-defined]
        assert data.integration_type == "mcp_server"  # type: ignore[attr-defined]
        assert data.result_status == "available"  # type: ignore[attr-defined]
        assert data.synced_count == 10  # type: ignore[attr-defined]
        assert data.updated_count == 3  # type: ignore[attr-defined]
        assert data.missing_count == 2  # type: ignore[attr-defined]
        assert data.error_type is None
        assert data.error_message is None

    def test_none_result_status(self) -> None:
        """Should handle None result_status gracefully."""
        handler = IntegrationRefreshHandler()
        event = self._make_event(result_status=None)

        audit_event = handler.handle(event)

        assert audit_event.structured_data.result_status is None  # type: ignore[attr-defined]
