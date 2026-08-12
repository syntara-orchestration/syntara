"""Tests for audit event emission from RoleAssignmentService.

Verifies that RoleAssignmentService methods correctly dispatch
RoleAssignmentEvent domain events which are converted to AuditEvents
by the registered handler.
"""

# mypy: disable-error-code="attr-defined"

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.authz.audit.role_assignment import RoleAssignmentEvent, RoleAssignmentHandler
from syntara.authz.models.assignments import RoleAssignment
from syntara.authz.services.role_assignment_service import RoleAssignmentService
from syntara.core.models import User

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent


class TestRoleAssignmentServiceAssignAuditEvents:
    """Tests for audit event emission from RoleAssignmentService.assign()."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({RoleAssignmentEvent: RoleAssignmentHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_assign_user_role_emits_role_assigned_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Successful user role assignment should emit a role_assigned audit event."""
        assignment_id = uuid4()
        principal_id = uuid4()

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()

        # exec().first() must return None (no existing assignment)
        mock_exec_result = Mock()
        mock_exec_result.first.return_value = None
        mock_session.exec = AsyncMock(return_value=mock_exec_result)

        async def fake_refresh(obj: RoleAssignment) -> None:
            obj.id = assignment_id

        mock_session.refresh = AsyncMock(side_effect=fake_refresh)

        service = RoleAssignmentService(session=mock_session, current_user=test_user)

        with (
            patch.object(
                service,
                "_validate_principal_id",
                new_callable=AsyncMock,
                return_value=("alice", "user"),
            ),
            patch.object(service, "_validate_role", new_callable=AsyncMock),
            patch.object(service, "_resolve_project_name", new_callable=AsyncMock, return_value=None),
            patch.object(service, "_enrich_with_role_info", new_callable=AsyncMock),
        ):
            await service.assign(
                principal_id=principal_id,
                role_name="editor",
            )

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "role_assigned"
        assert event.event_category == EventCategory.SECURITY_EVENT
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.authz"
        assert event.event_message == "Role assigned: editor -> user alice"
        assert event.resource_urn == f"urn:syntara:role-assignment:{assignment_id}"

        assert event.structured_data.data_type == "role-assignment"
        assert event.structured_data.action == "assigned"
        assert event.structured_data.principal_type == "user"
        assert event.structured_data.principal_name == "alice"
        assert event.structured_data.role_name == "editor"

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_assign_group_role_emits_role_assigned_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Group role assignment should emit event with group_name."""
        assignment_id = uuid4()
        group_id = uuid4()

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()

        mock_exec_result = Mock()
        mock_exec_result.first.return_value = None
        mock_session.exec = AsyncMock(return_value=mock_exec_result)

        async def fake_refresh(obj: RoleAssignment) -> None:
            obj.id = assignment_id

        mock_session.refresh = AsyncMock(side_effect=fake_refresh)

        service = RoleAssignmentService(session=mock_session, current_user=test_user)

        with (
            patch.object(service, "_validate_group_id", new_callable=AsyncMock, return_value="developers"),
            patch.object(service, "_validate_role", new_callable=AsyncMock),
            patch.object(service, "_resolve_project_name", new_callable=AsyncMock, return_value=None),
            patch.object(service, "_enrich_with_role_info", new_callable=AsyncMock),
        ):
            await service.assign(
                group_id=group_id,
                role_name="viewer",
            )

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "role_assigned"
        assert event.event_message == "Role assigned: viewer -> group developers"
        assert event.structured_data.group_name == "developers"

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_assign_with_project_includes_project_in_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Project-scoped assignment should include project_id in structured_data."""
        assignment_id = uuid4()
        principal_id = uuid4()
        project_id = uuid4()

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()

        mock_exec_result = Mock()
        mock_exec_result.first.return_value = None
        mock_session.exec = AsyncMock(return_value=mock_exec_result)

        async def fake_refresh(obj: RoleAssignment) -> None:
            obj.id = assignment_id

        mock_session.refresh = AsyncMock(side_effect=fake_refresh)

        service = RoleAssignmentService(session=mock_session, current_user=test_user)

        with (
            patch.object(service, "_validate_principal_id", new_callable=AsyncMock, return_value=("bob", "user")),
            patch.object(service, "_validate_role", new_callable=AsyncMock),
            patch.object(service, "_resolve_project_name", new_callable=AsyncMock, return_value="my-project"),
            patch.object(service, "_enrich_with_role_info", new_callable=AsyncMock),
            patch("syntara.core.queries.project_queries.assert_project_alive", new_callable=AsyncMock),
        ):
            await service.assign(
                principal_id=principal_id,
                role_name="editor",
                project_id=project_id,
            )

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]
        assert event.structured_data.project_id == str(project_id)


class TestRoleAssignmentServiceRevokeAuditEvents:
    """Tests for audit event emission from RoleAssignmentService.revoke()."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({RoleAssignmentEvent: RoleAssignmentHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_revoke_assignment_emits_role_revoked_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Successful revocation should emit a role_revoked audit event."""
        assignment_id = uuid4()
        principal_id = uuid4()

        assignment = RoleAssignment(
            id=assignment_id,
            principal_id=principal_id,
            role_name="editor",
            project_id=None,
            is_builtin=False,
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        mock_session.delete = AsyncMock()

        mock_exec_result = Mock()
        mock_exec_result.first.return_value = assignment
        mock_session.exec = AsyncMock(return_value=mock_exec_result)

        service = RoleAssignmentService(session=mock_session, current_user=test_user)

        with patch.object(
            service,
            "_resolve_assignment_identity",
            new_callable=AsyncMock,
            return_value=("alice", "user", None),
        ):
            await service.revoke(assignment_id)

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "role_revoked"
        assert event.event_category == EventCategory.SECURITY_EVENT
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.authz"
        assert event.resource_urn == f"urn:syntara:role-assignment:{assignment_id}"
        assert event.event_message == "Role revoked: editor -> user alice"
        assert event.structured_data.action == "revoked"
        assert event.structured_data.role_name == "editor"
        assert event.structured_data.principal_type == "user"
        assert event.structured_data.principal_name == "alice"
