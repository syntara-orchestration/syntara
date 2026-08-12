"""Unit tests for IntegrationValidateEvent and handler."""

from uuid import uuid4

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.integrations.audit.integration_validate import (
    IntegrationValidateEvent,
    IntegrationValidateHandler,
)
from syntara.integrations.models.integration import IntegrationStatus


class TestIntegrationValidateHandler:
    """Tests for IntegrationValidateHandler."""

    def _make_event(self, **overrides: object) -> IntegrationValidateEvent:
        defaults: dict[str, object] = {
            "integration_name": "GitHub MCP",
            "integration_type": "mcp_server",
            "integration_id": uuid4(),
            "timeout": False,
            "result_status": IntegrationStatus.AVAILABLE,
            "error_type": None,
        }
        defaults.update(overrides)
        return IntegrationValidateEvent(**defaults)  # type: ignore[arg-type]

    def test_success_event(self) -> None:
        """Should produce INFO event for successful validation."""
        handler = IntegrationValidateHandler()
        event = self._make_event()

        audit_event = handler.handle(event)

        assert audit_event.event_action == "integration_validated"
        assert audit_event.event_category == EventCategory.SYSTEM_OPERATION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.source_component == "syntara.integrations.integration"
        assert "GitHub MCP" in audit_event.event_message
        assert "successful" in audit_event.event_message

    def test_validation_failure(self) -> None:
        """Should produce WARNING ERROR event for validation failure."""
        handler = IntegrationValidateHandler()
        event = self._make_event(
            error_type="HealthCheckFailed",
            result_status=IntegrationStatus.ERROR,
        )

        audit_event = handler.handle(event)

        assert audit_event.event_severity == EventSeverity.WARNING
        assert audit_event.event_status == EventStatus.ERROR
        assert "failed" in audit_event.event_message
        assert audit_event.structured_data.error_message == "Look at the Operational Logs for full diagnosis"
        assert audit_event.structured_data.error_type == "HealthCheckFailed"

    def test_validation_timeout(self) -> None:
        """Should produce WARNING ERROR event for validation timeout."""
        handler = IntegrationValidateHandler()
        event = self._make_event(
            error_type="TimeoutError",
            timeout=True,
        )

        audit_event = handler.handle(event)

        assert audit_event.event_severity == EventSeverity.WARNING
        assert audit_event.event_status == EventStatus.ERROR
        assert "timeout" in audit_event.event_message
        assert audit_event.structured_data.timeout is True  # type: ignore[attr-defined]

    def test_resource_fields_with_integration_id(self) -> None:
        """Should set resource URN when integration_id is present."""
        handler = IntegrationValidateHandler()
        integration_id = uuid4()
        event = self._make_event(integration_id=integration_id, integration_name="Test Integration")

        audit_event = handler.handle(event)

        assert audit_event.resource_urn == f"urn:syntara:integration:{integration_id}"
        assert audit_event.resource_name == "Test Integration"

    def test_resource_fields_without_integration_id(self) -> None:
        """Should not set resource URN when integration_id is None."""
        handler = IntegrationValidateHandler()
        event = self._make_event(integration_id=None)

        audit_event = handler.handle(event)

        assert audit_event.resource_urn is None
        assert audit_event.resource_name == "GitHub MCP"

    def test_structured_data_fields(self) -> None:
        """Should include all relevant fields in structured data."""
        handler = IntegrationValidateHandler()
        event = self._make_event(
            integration_name="Slack MCP",
            integration_type="mcp_server",
            timeout=False,
            result_status=IntegrationStatus.AVAILABLE,
        )

        audit_event = handler.handle(event)
        data = audit_event.structured_data

        assert data.data_type == "integration-validate-context"
        assert data.integration_name == "Slack MCP"  # type: ignore[attr-defined]
        assert data.integration_type == "mcp_server"  # type: ignore[attr-defined]
        assert data.timeout is False  # type: ignore[attr-defined]
        assert data.result_status == "available"  # type: ignore[attr-defined]
        assert data.error_type is None
        assert data.error_message is None

    def test_none_result_status(self) -> None:
        """Should handle None result_status gracefully."""
        handler = IntegrationValidateHandler()
        event = self._make_event(result_status=None)

        audit_event = handler.handle(event)

        assert audit_event.structured_data.result_status is None  # type: ignore[attr-defined]
