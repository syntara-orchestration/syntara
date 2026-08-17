"""Integration tests for audit event emission from IntegrationService.

These tests verify that service methods correctly dispatch domain events
which are then converted to AuditEvents by the registered handlers.
"""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models import User
from syntara.integrations.exceptions import IntegrationNameConflictError, IntegrationNotFoundError
from syntara.integrations.models.integration import (
    IntegrationCreate,
    IntegrationType,
    IntegrationUpdate,
)
from syntara.integrations.services.integration_service import IntegrationService


def _mcp_create(name: str = "Test MCP", **kwargs: object) -> IntegrationCreate:
    defaults: dict[str, object] = {
        "name": name,
        "integration_type": IntegrationType.MCP_SERVER,
        "configuration": {"integration_type": "mcp_server", "base_url": "http://localhost:8080"},
    }
    defaults.update(kwargs)
    return IntegrationCreate(**defaults)


@pytest.fixture
def integration_service(test_db_session: AsyncSession, test_user: User) -> IntegrationService:
    return IntegrationService(test_db_session, test_user)


class TestIntegrationServiceAuditEvents:
    """Tests for audit event emission from IntegrationService methods.

    These tests use a real AuditEventDispatcher with real handlers (no mock
    fixtures) so the full event pipeline runs end-to-end. Events are captured
    at the lowest level (_do_emit_audit_event) to verify correct emission.
    """

    def setup_method(self) -> None:
        """Register integrations audit handlers before each test."""
        from syntara.integrations.audit.integration_create import (
            IntegrationCreateEvent,
            IntegrationCreateHandler,
        )
        from syntara.integrations.audit.integration_delete import (
            IntegrationDeleteEvent,
            IntegrationDeleteHandler,
        )
        from syntara.integrations.audit.integration_update import (
            IntegrationUpdateEvent,
            IntegrationUpdateHandler,
        )
        from syntara.integrations.audit.integration_validate import (
            IntegrationValidateEvent,
            IntegrationValidateHandler,
        )

        AuditEventDispatcher.register(
            {
                IntegrationCreateEvent: IntegrationCreateHandler(),
                IntegrationUpdateEvent: IntegrationUpdateHandler(),
                IntegrationDeleteEvent: IntegrationDeleteHandler(),
                IntegrationValidateEvent: IntegrationValidateHandler(),
            }
        )

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_create_integration_success_emits_audit_event(
        self,
        mock_do_emit: object,
        integration_service: IntegrationService,
    ) -> None:
        """Successful create_integration should emit IntegrationCreateEvent."""
        data = _mcp_create("Slack MCP", description="Slack integration via MCP")

        await integration_service.create_integration(data)

        assert mock_do_emit.call_count == 1  # type: ignore[attr-defined]
        event: AuditEvent = mock_do_emit.call_args.args[0]  # type: ignore[attr-defined]

        assert event.event_action == "integration_created"
        assert event.event_category == EventCategory.SYSTEM_OPERATION
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.integrations.integration"
        assert event.event_message == "Integration created: Slack MCP"
        assert isinstance(event.structured_data, AuditContextData)
        assert event.structured_data.integration_name == "Slack MCP"  # type: ignore[attr-defined]
        assert event.structured_data.integration_type == "mcp_server"  # type: ignore[attr-defined]
        assert event.structured_data.initial_status == "unknown"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_create_integration_duplicate_name_emits_error_event(
        self,
        mock_do_emit: object,
        integration_service: IntegrationService,
    ) -> None:
        """Duplicate name during create_integration should emit error audit event."""
        data = _mcp_create("Duplicate Integration")

        await integration_service.create_integration(data)
        mock_do_emit.reset_mock()  # type: ignore[attr-defined]

        with pytest.raises(IntegrationNameConflictError):
            await integration_service.create_integration(data)

        assert mock_do_emit.call_count == 1  # type: ignore[attr-defined]
        event: AuditEvent = mock_do_emit.call_args.args[0]  # type: ignore[attr-defined]

        assert event.event_action == "integration_created"
        assert event.event_severity == EventSeverity.ERROR
        assert event.event_status == EventStatus.ERROR
        assert event.structured_data.error_type == "IntegrityError"

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_update_integration_success_emits_audit_event(
        self,
        mock_do_emit: object,
        integration_service: IntegrationService,
    ) -> None:
        """Successful update_integration should emit IntegrationUpdateEvent with tracked fields."""
        created = await integration_service.create_integration(_mcp_create("Original Name"))
        mock_do_emit.reset_mock()  # type: ignore[attr-defined]

        patch_data = IntegrationUpdate(name="Updated Name", description="New description")
        await integration_service.update_integration(created.id, patch_data)

        assert mock_do_emit.call_count == 1  # type: ignore[attr-defined]
        event: AuditEvent = mock_do_emit.call_args.args[0]  # type: ignore[attr-defined]

        assert event.event_action == "integration_updated"
        assert event.event_category == EventCategory.SYSTEM_OPERATION
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.event_message == "Integration updated: Updated Name"
        assert isinstance(event.structured_data, AuditContextData)
        assert event.structured_data.integration_name == "Updated Name"  # type: ignore[attr-defined]
        assert set(event.structured_data.updated_fields) == {"name", "description"}  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_update_integration_tracks_only_set_fields(
        self,
        mock_do_emit: object,
        integration_service: IntegrationService,
    ) -> None:
        """update_integration should emit audit event with only the fields that were set."""
        created = await integration_service.create_integration(_mcp_create("Integration"))
        mock_do_emit.reset_mock()  # type: ignore[attr-defined]

        patch_data = IntegrationUpdate(description="Updated description only")
        await integration_service.update_integration(created.id, patch_data)

        assert mock_do_emit.call_count == 1  # type: ignore[attr-defined]
        event: AuditEvent = mock_do_emit.call_args.args[0]  # type: ignore[attr-defined]

        assert event.event_action == "integration_updated"
        assert event.structured_data.updated_fields == ["description"]  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_delete_integration_success_emits_audit_event(
        self,
        mock_do_emit: object,
        integration_service: IntegrationService,
    ) -> None:
        """Successful delete_integration should emit IntegrationDeleteEvent with tool count."""
        created = await integration_service.create_integration(_mcp_create("To Delete"))
        mock_do_emit.reset_mock()  # type: ignore[attr-defined]

        await integration_service.delete_integration(created.id)

        assert mock_do_emit.call_count == 1  # type: ignore[attr-defined]
        event: AuditEvent = mock_do_emit.call_args.args[0]  # type: ignore[attr-defined]

        assert event.event_action == "integration_deleted"
        assert event.event_category == EventCategory.SYSTEM_OPERATION
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.event_message == "Integration deleted: To Delete"
        assert isinstance(event.structured_data, AuditContextData)
        assert event.structured_data.tools_deleted == 0  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_delete_integration_not_found_emits_error_event(
        self,
        mock_do_emit: object,
        integration_service: IntegrationService,
    ) -> None:
        """delete_integration should emit error event when integration not found."""
        non_existent_id = uuid4()

        with pytest.raises(IntegrationNotFoundError):
            await integration_service.delete_integration(non_existent_id)

        assert mock_do_emit.call_count == 1  # type: ignore[attr-defined]
        event: AuditEvent = mock_do_emit.call_args.args[0]  # type: ignore[attr-defined]

        assert event.event_action == "integration_deleted"
        assert event.event_severity == EventSeverity.ERROR
        assert event.event_status == EventStatus.ERROR
        assert event.structured_data.error_type == "IntegrationNotFoundError"

    @pytest.mark.asyncio
    async def test_validate_integration_success_emits_audit_event(
        self,
        integration_service: IntegrationService,
    ) -> None:
        """Successful validate_integration should emit IntegrationValidateEvent."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from syntara.integrations.adapters.protocol import ValidateResult

        success_result = ValidateResult(success=True, checked_at=datetime.now(UTC))
        mock_settings = MagicMock()
        mock_settings.get = AsyncMock(return_value=10)

        created = await integration_service.create_integration(_mcp_create("MCP Server"))

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch(
                "syntara.integrations.adapters.mcp_server.MCPServerAdapter.validate",
                new=AsyncMock(return_value=success_result),
            ),
            patch(
                "syntara.integrations.services.integration_service.get_runtime_settings",
                return_value=mock_settings,
            ),
        ):
            await integration_service.validate_integration(created.id)

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "integration_validated"
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert isinstance(event.structured_data, AuditContextData)
        assert event.structured_data.error_type is None
        assert event.structured_data.result_status == "available"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_validate_integration_failure_emits_error_event(
        self,
        integration_service: IntegrationService,
    ) -> None:
        """A failed health check should emit an error audit event."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from syntara.integrations.adapters.protocol import ValidateResult

        fail_result = ValidateResult(success=False, error="Connection refused", checked_at=datetime.now(UTC))
        mock_settings = MagicMock()
        mock_settings.get = AsyncMock(return_value=10)

        created = await integration_service.create_integration(_mcp_create("Broken MCP"))

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch(
                "syntara.integrations.adapters.mcp_server.MCPServerAdapter.validate",
                new=AsyncMock(return_value=fail_result),
            ),
            patch(
                "syntara.integrations.services.integration_service.get_runtime_settings",
                return_value=mock_settings,
            ),
        ):
            await integration_service.validate_integration(created.id)

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "integration_validated"
        assert event.event_severity == EventSeverity.WARNING
        assert event.event_status == EventStatus.ERROR
        assert event.structured_data.error_type == "HealthCheckFailed"
        assert event.structured_data.result_status == "error"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_validate_integration_failure_preserves_error_message(
        self,
        integration_service: IntegrationService,
    ) -> None:
        """Verify ValidateResult.error message is preserved in audit event.

        This test ensures that error messages from the health check adapter
        flow end-to-end through integration_service.py (line 475) and
        integration_validate.py (lines 71-72) into the audit event.
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        from syntara.integrations.adapters.protocol import ValidateResult

        fail_result = ValidateResult(
            success=False,
            error="Connection refused: socket timeout after 30s",
            checked_at=datetime.now(UTC),
        )
        mock_settings = MagicMock()
        mock_settings.get = AsyncMock(return_value=10)

        created = await integration_service.create_integration(_mcp_create("Slow Server"))

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch(
                "syntara.integrations.adapters.mcp_server.MCPServerAdapter.validate",
                new=AsyncMock(return_value=fail_result),
            ),
            patch(
                "syntara.integrations.services.integration_service.get_runtime_settings",
                return_value=mock_settings,
            ),
        ):
            await integration_service.validate_integration(created.id)

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        # Verify the error message from ValidateResult is preserved in the audit event
        assert event.structured_data.error_message == "Connection refused: socket timeout after 30s"
