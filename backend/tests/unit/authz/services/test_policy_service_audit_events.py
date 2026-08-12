"""Tests for audit event emission from PolicyService.

Verifies that PolicyService methods correctly dispatch PolicyLifecycleEvent
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
from syntara.authz.audit.policy_lifecycle import PolicyLifecycleEvent, PolicyLifecycleHandler
from syntara.authz.models.policy import Policy
from syntara.authz.services.policy_service import PolicyService
from syntara.core.models import User

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent


class TestPolicyServiceCreateAuditEvents:
    """Tests for audit event emission from PolicyService.create_policy()."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({PolicyLifecycleEvent: PolicyLifecycleHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_create_policy_emits_policy_created_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Successful policy creation should emit a policy_created audit event."""
        policy_id = uuid4()
        statements = [{"effect": "allow", "actions": ["role:read"], "scope": "any"}]

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()

        async def fake_refresh(obj: Policy) -> None:
            obj.id = policy_id
            obj.name = "test-policy"
            obj.description = "Test policy"
            obj.is_builtin = False
            obj.scope = "any"
            obj.statements = statements
            obj.project_id = None

        mock_session.refresh = AsyncMock(side_effect=fake_refresh)

        service = PolicyService(session=mock_session, user=test_user)

        with (
            patch.object(service, "_check_name_conflict", new_callable=AsyncMock),
            patch.object(PolicyService, "_validate_resource_actions"),
            patch.object(PolicyService, "_validate_no_deny_effect"),
            patch("syntara.authz.services.policy_service.is_builtin_policy", return_value=False),
        ):
            await service.create_policy(
                name="test-policy",
                statements=statements,
                description="Test policy",
            )

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "policy_created"
        assert event.event_category == EventCategory.SECURITY_EVENT
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.authz"
        assert event.event_message == "Policy created: test-policy"
        assert event.resource_urn == f"urn:syntara:policy:{policy_id}"
        assert event.structured_data.data_type == "policy-lifecycle"
        assert event.structured_data.action == "created"
        assert event.structured_data.policy_name == "test-policy"

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_create_policy_with_project_emits_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Policy created with project_id should emit audit event."""
        policy_id = uuid4()
        project_id = uuid4()
        statements = [{"effect": "allow", "actions": ["role:read"], "scope": "project"}]

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()

        async def fake_refresh(obj: Policy) -> None:
            obj.id = policy_id
            obj.name = "project-policy"
            obj.project_id = project_id
            obj.scope = "project"
            obj.is_builtin = False
            obj.statements = statements

        mock_session.refresh = AsyncMock(side_effect=fake_refresh)

        service = PolicyService(session=mock_session, user=test_user)

        with (
            patch.object(service, "_check_name_conflict", new_callable=AsyncMock),
            patch.object(PolicyService, "_validate_resource_actions"),
            patch.object(PolicyService, "_validate_no_deny_effect"),
            patch.object(PolicyService, "_validate_project_statements"),
            patch("syntara.authz.services.policy_service.is_builtin_policy", return_value=False),
            patch("syntara.core.queries.project_queries.assert_project_alive", new_callable=AsyncMock),
        ):
            await service.create_policy(
                name="project-policy",
                statements=statements,
                project_id=project_id,
            )

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]
        assert event.event_action == "policy_created"
        assert event.resource_urn == f"urn:syntara:policy:{policy_id}"


class TestPolicyServiceUpdateAuditEvents:
    """Tests for audit event emission from PolicyService.update_policy()."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({PolicyLifecycleEvent: PolicyLifecycleHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_update_policy_emits_policy_updated_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Successful policy update should emit a policy_updated audit event."""
        policy_id = uuid4()
        existing_policy = Policy(
            id=policy_id,
            name="custom-policy",
            description="Original",
            is_builtin=False,
            scope="any",
            statements=[{"effect": "allow", "actions": ["role:read"], "scope": "any"}],
            labels={},
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        service = PolicyService(session=mock_session, user=test_user)

        with (
            patch.object(service, "get_policy_read", return_value=None),
            patch.object(service, "get_policy", new_callable=AsyncMock, return_value=existing_policy),
        ):
            await service.update_policy(policy_id, description="Updated description")

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "policy_updated"
        assert event.event_category == EventCategory.SECURITY_EVENT
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.authz"
        assert event.resource_urn == f"urn:syntara:policy:{policy_id}"


class TestPolicyServiceDeleteAuditEvents:
    """Tests for audit event emission from PolicyService.delete_policy()."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({PolicyLifecycleEvent: PolicyLifecycleHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_delete_policy_no_roles_emits_info_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Deleting a policy with no role references should emit INFO severity."""
        policy_id = uuid4()
        existing_policy = Policy(
            id=policy_id,
            name="unused-policy",
            is_builtin=False,
            scope="any",
            statements=[],
            labels={},
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        mock_session.delete = AsyncMock()

        mock_exec_result = Mock()
        mock_exec_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_exec_result)

        service = PolicyService(session=mock_session, user=test_user)

        with (
            patch.object(service, "get_policy_read", return_value=None),
            patch.object(service, "get_policy", new_callable=AsyncMock, return_value=existing_policy),
        ):
            await service.delete_policy(policy_id)

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "policy_deleted"
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert not hasattr(event.structured_data, "affected_roles_count")

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_delete_policy_with_roles_emits_warning_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Deleting a policy referenced by roles should emit WARNING severity."""
        policy_id = uuid4()
        existing_policy = Policy(
            id=policy_id,
            name="active-policy",
            is_builtin=False,
            scope="any",
            statements=[],
            labels={},
        )

        mock_roles = [Mock(policy_names=["active-policy"]), Mock(policy_names=["active-policy"])]

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        mock_session.delete = AsyncMock()

        mock_exec_result = Mock()
        mock_exec_result.all.return_value = mock_roles
        mock_session.exec = AsyncMock(return_value=mock_exec_result)

        service = PolicyService(session=mock_session, user=test_user)

        with (
            patch.object(service, "get_policy_read", return_value=None),
            patch.object(service, "get_policy", new_callable=AsyncMock, return_value=existing_policy),
        ):
            await service.delete_policy(policy_id)

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "policy_deleted"
        assert event.event_severity == EventSeverity.WARNING
        assert event.structured_data.affected_roles_count == 2
