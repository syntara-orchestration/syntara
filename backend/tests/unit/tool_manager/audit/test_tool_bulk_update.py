"""Unit tests for ToolBulkUpdateEvent and handler."""

from uuid import uuid4

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.tool_manager.audit.tool_bulk_update import (
    ToolBulkUpdateEvent,
    ToolBulkUpdateHandler,
)


class TestToolBulkUpdateHandler:
    """Tests for ToolBulkUpdateHandler."""

    def _make_event(self, **overrides: object) -> ToolBulkUpdateEvent:
        defaults: dict[str, object] = {
            "tool_ids": [uuid4(), uuid4(), uuid4()],
            "enabled": True,
            "updated_count": 3,
            "skipped_count": 0,
            "duplicate_count": 0,
            "not_found_count": 0,
        }
        defaults.update(overrides)
        return ToolBulkUpdateEvent(**defaults)  # type: ignore[arg-type]

    def test_success_event_enabled(self) -> None:
        """Should produce INFO SYSTEM_OPERATION event for successful enable."""
        handler = ToolBulkUpdateHandler()
        event = self._make_event()

        audit_event = handler.handle(event)

        assert audit_event.event_action == "tools_bulk_updated"
        assert audit_event.event_category == EventCategory.SYSTEM_OPERATION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.source_component == "syntara.tool_manager.tool"
        assert "3 tools enabled" in audit_event.event_message
        assert "completed" in audit_event.event_message

    def test_success_event_disabled(self) -> None:
        """Should produce INFO event for successful disable."""
        handler = ToolBulkUpdateHandler()
        event = self._make_event(enabled=False)

        audit_event = handler.handle(event)

        assert "3 tools disabled" in audit_event.event_message

    def test_success_event_with_skipped(self) -> None:
        """Should include skipped count in message when present."""
        handler = ToolBulkUpdateHandler()
        event = self._make_event(updated_count=2, skipped_count=1)

        audit_event = handler.handle(event)

        assert "2 tools enabled" in audit_event.event_message
        assert "1 skipped" in audit_event.event_message

    def test_error_event(self) -> None:
        """Should produce ERROR event when error_type is set."""
        handler = ToolBulkUpdateHandler()
        event = self._make_event(error_type="ToolBulkUpdateValidationError")

        audit_event = handler.handle(event)

        assert audit_event.event_severity == EventSeverity.ERROR
        assert audit_event.event_status == EventStatus.ERROR
        assert "failed" in audit_event.event_message
        assert audit_event.structured_data.error_type == "ToolBulkUpdateValidationError"
        assert audit_event.structured_data.error_message == "Look at the Operational Logs for full diagnosis"

    def test_no_resource_fields(self) -> None:
        """Should not set resource URN/name for bulk operations."""
        handler = ToolBulkUpdateHandler()
        event = self._make_event()

        audit_event = handler.handle(event)

        assert audit_event.resource_urn is None
        assert audit_event.resource_name is None

    def test_structured_data_fields(self) -> None:
        """Should include all relevant fields in structured data."""
        handler = ToolBulkUpdateHandler()
        tool_ids = [uuid4(), uuid4(), uuid4(), uuid4()]
        event = self._make_event(
            tool_ids=tool_ids,
            enabled=True,
            updated_count=3,
            skipped_count=1,
            duplicate_count=2,
            not_found_count=0,
        )

        audit_event = handler.handle(event)
        data = audit_event.structured_data

        assert data.data_type == "tool-bulk-update-context"
        assert data.tool_count == 4  # type: ignore[attr-defined]
        assert data.enabled is True  # type: ignore[attr-defined]
        assert data.updated_count == 3  # type: ignore[attr-defined]
        assert data.skipped_count == 1  # type: ignore[attr-defined]
        assert data.duplicate_count == 2  # type: ignore[attr-defined]
        assert data.not_found_count == 0  # type: ignore[attr-defined]
        assert data.error_type is None

    def test_zero_updates(self) -> None:
        """Should handle zero updates (all skipped)."""
        handler = ToolBulkUpdateHandler()
        event = self._make_event(
            updated_count=0,
            skipped_count=3,
            not_found_count=1,
        )

        audit_event = handler.handle(event)

        assert "0 tools enabled" in audit_event.event_message
        assert "3 skipped" in audit_event.event_message
        assert audit_event.structured_data.updated_count == 0  # type: ignore[attr-defined]

    def test_empty_tool_ids_list(self) -> None:
        """Should handle empty tool_ids list."""
        handler = ToolBulkUpdateHandler()
        event = self._make_event(tool_ids=[])

        audit_event = handler.handle(event)

        assert audit_event.structured_data.tool_count == 0  # type: ignore[attr-defined]

    def test_duplicates_only(self) -> None:
        """Should track duplicate count separately."""
        handler = ToolBulkUpdateHandler()
        event = self._make_event(duplicate_count=5)

        audit_event = handler.handle(event)

        assert audit_event.structured_data.duplicate_count == 5  # type: ignore[attr-defined]

    def test_message_without_skipped(self) -> None:
        """Should not include skipped in message when count is zero."""
        handler = ToolBulkUpdateHandler()
        event = self._make_event(updated_count=3, skipped_count=0)

        audit_event = handler.handle(event)

        assert "skipped" not in audit_event.event_message
        assert "3 tools enabled" in audit_event.event_message
