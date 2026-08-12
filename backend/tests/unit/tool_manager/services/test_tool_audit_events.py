"""Integration tests for audit event emission from ToolService.

These tests verify that service methods correctly dispatch domain events
which are then converted to AuditEvents by the registered handlers.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.tool_manager.exceptions import ToolNotFoundError
from syntara.tool_manager.models.tool import Tool, ToolUpdate
from syntara.tool_manager.services.tool_service import ToolService


class TestToolServiceAuditEvents:
    """Tests for audit event emission from ToolService methods.

    These tests use a real AuditEventDispatcher with real handlers (no mock
    fixtures) so the full event pipeline runs end-to-end. Events are captured
    at the lowest level (_do_emit_audit_event) to verify correct emission.
    """

    def setup_method(self) -> None:
        """Register tool_manager audit handlers before each test."""
        from syntara.tool_manager.audit.tool_bulk_update import (
            ToolBulkUpdateEvent,
            ToolBulkUpdateHandler,
        )
        from syntara.tool_manager.audit.tool_update import (
            ToolUpdateEvent,
            ToolUpdateHandler,
        )

        AuditEventDispatcher.register(
            {
                ToolUpdateEvent: ToolUpdateHandler(),
                ToolBulkUpdateEvent: ToolBulkUpdateHandler(),
            }
        )

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_update_tool_success_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_tool: Tool,
        test_tool_service: ToolService,
    ) -> None:
        """Successful update_tool should emit ToolUpdateEvent with tracked fields."""
        tool_update = ToolUpdate(enabled=False)

        await test_tool_service.update_tool(test_tool.id, tool_update)

        # Verify audit event was emitted
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "tool_updated"
        assert event.event_category == EventCategory.SYSTEM_OPERATION
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.tool_manager.tool"
        assert f"Tool updated: {test_tool.name}" in event.event_message
        assert "enabled" in event.event_message
        assert isinstance(event.structured_data, AuditContextData)
        assert event.structured_data.tool_name == test_tool.name  # type: ignore[attr-defined]
        assert event.structured_data.updated_fields == ["enabled"]  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_update_tool_tracks_only_modified_fields(
        self,
        mock_do_emit: AsyncMock,
        test_tool: Tool,
        test_tool_service: ToolService,
    ) -> None:
        """update_tool should emit audit event with only the fields that were patched."""
        # Patch multiple fields
        tool_update = ToolUpdate(enabled=False, refresh_error="Connection timeout")

        await test_tool_service.update_tool(test_tool.id, tool_update)

        # Verify audit event includes all patched fields
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "tool_updated"
        # Order might vary, so check both fields are present
        updated_fields = event.structured_data.updated_fields  # type: ignore[attr-defined]
        assert len(updated_fields) == 2
        assert "enabled" in updated_fields
        assert "refresh_error" in updated_fields

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_update_tool_not_found_emits_error_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_tool_service: ToolService,
    ) -> None:
        """update_tool should emit error audit event when tool not found."""
        non_existent_id = uuid4()
        tool_update = ToolUpdate(enabled=False)

        with pytest.raises(ToolNotFoundError):
            await test_tool_service.update_tool(non_existent_id, tool_update)

        # Verify error audit event was emitted
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "tool_updated"
        assert event.event_severity == EventSeverity.ERROR
        assert event.event_status == EventStatus.ERROR
        assert event.structured_data.error_type == "ToolNotFoundError"

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_bulk_update_tools_success_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_tool: Tool,
        test_tool_service: ToolService,
    ) -> None:
        """Successful bulk_update_tools should emit ToolBulkUpdateEvent with counts."""
        await test_tool_service.bulk_update_tools(
            tool_ids=[test_tool.id],
            enabled=False,
        )

        # Verify audit event was emitted
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "tools_bulk_updated"
        assert event.event_category == EventCategory.SYSTEM_OPERATION
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.tool_manager.tool"
        assert "disabled" in event.event_message
        assert isinstance(event.structured_data, AuditContextData)
        assert event.structured_data.enabled is False  # type: ignore[attr-defined]
        assert event.structured_data.updated_count == 1  # type: ignore[attr-defined]
        assert event.structured_data.skipped_count == 0  # type: ignore[attr-defined]
        assert event.structured_data.duplicate_count == 0  # type: ignore[attr-defined]
        assert event.structured_data.not_found_count == 0  # type: ignore[attr-defined]
        assert event.resource_urn is None  # Bulk operation has no single resource

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_bulk_update_tools_with_duplicates_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_tool: Tool,
        test_tool_service: ToolService,
    ) -> None:
        """bulk_update_tools with duplicate IDs should emit audit event with duplicate count."""
        # Include duplicate ID
        await test_tool_service.bulk_update_tools(
            tool_ids=[test_tool.id, test_tool.id],
            enabled=True,
        )

        # Verify audit event includes duplicate count
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "tools_bulk_updated"
        assert event.structured_data.updated_count == 1  # type: ignore[attr-defined]
        assert event.structured_data.duplicate_count == 1  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_bulk_update_tools_with_not_found_emits_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_tool: Tool,
        test_tool_service: ToolService,
    ) -> None:
        """bulk_update_tools with non-existent IDs should emit audit event with not_found count."""
        non_existent_id = uuid4()

        await test_tool_service.bulk_update_tools(
            tool_ids=[test_tool.id, non_existent_id],
            enabled=False,
        )

        # Verify audit event includes not_found count
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "tools_bulk_updated"
        assert event.structured_data.updated_count == 1  # type: ignore[attr-defined]
        assert event.structured_data.not_found_count == 1  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_bulk_update_tools_empty_list_emits_error_audit_event(
        self,
        mock_do_emit: AsyncMock,
        test_tool_service: ToolService,
    ) -> None:
        """bulk_update_tools with empty list should emit error audit event."""
        from syntara.tool_manager.exceptions import ToolBulkUpdateValidationError

        with pytest.raises(ToolBulkUpdateValidationError):
            await test_tool_service.bulk_update_tools(
                tool_ids=[],
                enabled=True,
            )

        # Verify error audit event was emitted
        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "tools_bulk_updated"
        assert event.event_severity == EventSeverity.ERROR
        assert event.event_status == EventStatus.ERROR
        assert event.structured_data.error_type == "ToolBulkUpdateValidationError"
