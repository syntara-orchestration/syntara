"""Tests for audit event emission from RoleService.

Verifies that RoleService methods correctly dispatch RoleLifecycleEvent
domain events which are converted to AuditEvents by the registered handler.
"""

# mypy: disable-error-code="attr-defined"

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.authz.audit.role_lifecycle import RoleLifecycleEvent, RoleLifecycleHandler
from syntara.authz.models.role import Role
from syntara.authz.services.role_service import RoleService
from syntara.core.models import User

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent


class TestRoleServiceCreateAuditEvents:
    """Tests for audit event emission from RoleService.create_role()."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({RoleLifecycleEvent: RoleLifecycleHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_create_role_emits_role_created_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Successful role creation should emit a role_created audit event."""
        role_id = uuid4()
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()

        async def fake_refresh(obj: Role) -> None:
            obj.id = role_id
            obj.name = "test-editor"
            obj.description = "Test editor role"
            obj.is_builtin = False
            obj.scope = "system"
            obj.policy_names = ["read-all"]
            obj.project_id = None

        mock_session.refresh = AsyncMock(side_effect=fake_refresh)

        service = RoleService(session=mock_session, user=test_user)

        with (
            patch.object(service, "_check_name_conflict", new_callable=AsyncMock),
            patch.object(service, "_validate_policy_names", new_callable=AsyncMock),
        ):
            await service.create_role(
                name="test-editor",
                policies=["read-all"],
                description="Test editor role",
            )

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "role_created"
        assert event.event_category == EventCategory.SECURITY_EVENT
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.authz"
        assert event.event_message == "Role created: test-editor"
        assert event.resource_urn == f"urn:syntara:role:{role_id}"
        assert event.structured_data.data_type == "role-lifecycle"
        assert event.structured_data.action == "created"
        assert event.structured_data.role_name == "test-editor"

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_create_role_with_project_emits_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Role created with project_id should emit audit event with project context."""
        role_id = uuid4()
        project_id = uuid4()
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()

        async def fake_refresh(obj: Role) -> None:
            obj.id = role_id
            obj.name = "project-role"
            obj.project_id = project_id
            obj.scope = "project"
            obj.is_builtin = False
            obj.policy_names = ["project-read"]

        mock_session.refresh = AsyncMock(side_effect=fake_refresh)

        service = RoleService(session=mock_session, user=test_user)

        with (
            patch.object(service, "_check_name_conflict", new_callable=AsyncMock),
            patch.object(service, "_validate_policy_names", new_callable=AsyncMock),
            patch("syntara.authz.services.role_service.is_builtin_role", return_value=False),
            patch("syntara.core.queries.project_queries.assert_project_alive", new_callable=AsyncMock),
        ):
            await service.create_role(
                name="project-role",
                policies=["project-read"],
                project_id=project_id,
            )

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]
        assert event.event_action == "role_created"
        assert event.resource_urn == f"urn:syntara:role:{role_id}"


class TestRoleServiceUpdateAuditEvents:
    """Tests for audit event emission from RoleService.update_role()."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({RoleLifecycleEvent: RoleLifecycleHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_update_role_emits_role_updated_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Successful role update should emit a role_updated audit event."""
        role_id = uuid4()
        existing_role = Role(
            id=role_id,
            name="custom-role",
            description="Original",
            is_builtin=False,
            scope="system",
            policy_names=["read-all"],
            labels={},
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        service = RoleService(session=mock_session, user=test_user)

        with (
            patch.object(service, "get_role_read", return_value=None),
            patch.object(service, "get_role", new_callable=AsyncMock, return_value=existing_role),
        ):
            await service.update_role(role_id, description="Updated description")

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "role_updated"
        assert event.event_category == EventCategory.SECURITY_EVENT
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.authz"
        assert event.resource_urn == f"urn:syntara:role:{role_id}"


class TestRoleServiceDeleteAuditEvents:
    """Tests for audit event emission from RoleService.delete_role()."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({RoleLifecycleEvent: RoleLifecycleHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_delete_role_no_assignments_emits_info_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Deleting a role with no assignments should emit INFO severity."""
        role_id = uuid4()
        existing_role = Role(
            id=role_id,
            name="unused-role",
            description="No assignments",
            is_builtin=False,
            scope="system",
            policy_names=[],
            labels={},
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        mock_session.delete = AsyncMock()

        mock_exec_result = Mock()
        mock_exec_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_exec_result)

        service = RoleService(session=mock_session, user=test_user)

        with (
            patch.object(service, "get_role_read", return_value=None),
            patch.object(service, "get_role", new_callable=AsyncMock, return_value=existing_role),
        ):
            await service.delete_role(role_id)

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "role_deleted"
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert not hasattr(event.structured_data, "affected_assignments_count")

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_delete_role_with_assignments_emits_warning_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Deleting a role with active assignments should emit WARNING severity."""
        role_id = uuid4()
        existing_role = Role(
            id=role_id,
            name="active-role",
            is_builtin=False,
            scope="system",
            policy_names=["read-all"],
            labels={},
        )

        mock_assignments = [Mock(), Mock(), Mock()]

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        mock_session.delete = AsyncMock()

        mock_exec_result = Mock()
        mock_exec_result.all.return_value = mock_assignments
        mock_session.exec = AsyncMock(return_value=mock_exec_result)

        service = RoleService(session=mock_session, user=test_user)

        with (
            patch.object(service, "get_role_read", return_value=None),
            patch.object(service, "get_role", new_callable=AsyncMock, return_value=existing_role),
        ):
            await service.delete_role(role_id)

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "role_deleted"
        assert event.event_severity == EventSeverity.WARNING
        assert event.structured_data.affected_assignments_count == 3
