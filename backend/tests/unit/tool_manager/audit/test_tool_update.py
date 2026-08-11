"""Unit tests for ToolUpdateEvent and handler."""

from uuid import uuid4

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.tool_manager.audit.tool_update import ToolUpdateEvent, ToolUpdateHandler


class TestToolUpdateHandler:
    """Tests for ToolUpdateHandler."""

    def _make_event(self, **overrides: object) -> ToolUpdateEvent:
        defaults: dict[str, object] = {
            "tool_id": uuid4(),
            "tool_name": "create_issue",
            "namespaced_name": "github.create_issue",
            "integration_id": uuid4(),
            "updated_fields": ["enabled", "status"],
        }
        defaults.update(overrides)
        return ToolUpdateEvent(**defaults)  # type: ignore[arg-type]

    def test_success_event(self) -> None:
        """Should produce INFO CONFIGURATION_CHANGE event for successful update."""
        handler = ToolUpdateHandler()
        event = self._make_event()

        audit_event = handler.handle(event)

        assert audit_event.event_action == "tool_updated"
        assert audit_event.event_category == EventCategory.SYSTEM_OPERATION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.source_component == "syntara.tool_manager.tool"
        assert "create_issue" in audit_event.event_message
        assert "enabled, status" in audit_event.event_message

    def test_error_event(self) -> None:
        """Should produce ERROR event when error_type is set."""
        handler = ToolUpdateHandler()
        event = self._make_event(error_type="ToolNotFoundError")

        audit_event = handler.handle(event)

        assert audit_event.event_severity == EventSeverity.ERROR
        assert audit_event.event_status == EventStatus.ERROR
        assert "failed" in audit_event.event_message
        assert audit_event.structured_data.error_type == "ToolNotFoundError"
        assert audit_event.structured_data.error_message == "Look at the Operational Logs for full diagnosis"

    def test_resource_fields(self) -> None:
        """Should set resource URN and name correctly."""
        handler = ToolUpdateHandler()
        tool_id = uuid4()
        event = self._make_event(tool_id=tool_id, tool_name="list_repos")

        audit_event = handler.handle(event)

        assert audit_event.resource_urn == f"urn:syntara:tool:{tool_id}"
        assert audit_event.resource_name == "list_repos"

    def test_structured_data_fields(self) -> None:
        """Should include all relevant fields in structured data."""
        handler = ToolUpdateHandler()
        provider_id = uuid4()
        event = self._make_event(
            tool_name="send_message",
            namespaced_name="slack.send_message",
            integration_id=provider_id,
            updated_fields=["enabled"],
        )

        audit_event = handler.handle(event)
        data = audit_event.structured_data

        assert data.data_type == "tool-update-context"
        assert data.tool_name == "send_message"  # type: ignore[attr-defined]
        assert data.namespaced_name == "slack.send_message"  # type: ignore[attr-defined]
        assert data.integration_id == str(provider_id)  # type: ignore[attr-defined]
        assert data.updated_fields == ["enabled"]  # type: ignore[attr-defined]
        assert data.error_type is None

    def test_empty_updated_fields(self) -> None:
        """Should handle empty updated_fields list."""
        handler = ToolUpdateHandler()
        event = self._make_event(updated_fields=[])

        audit_event = handler.handle(event)

        assert "none" in audit_event.event_message
        assert audit_event.structured_data.updated_fields == []  # type: ignore[attr-defined]

    def test_single_field_update(self) -> None:
        """Should handle single field update."""
        handler = ToolUpdateHandler()
        event = self._make_event(updated_fields=["refresh_error"])

        audit_event = handler.handle(event)

        assert "refresh_error" in audit_event.event_message
        assert audit_event.structured_data.updated_fields == ["refresh_error"]  # type: ignore[attr-defined]

    def test_all_fields_updated(self) -> None:
        """Should handle all fields being updated."""
        handler = ToolUpdateHandler()
        event = self._make_event(updated_fields=["enabled", "status", "refresh_error"])

        audit_event = handler.handle(event)

        assert audit_event.structured_data.updated_fields == ["enabled", "status", "refresh_error"]  # type: ignore[attr-defined]
        assert "enabled, status, refresh_error" in audit_event.event_message
