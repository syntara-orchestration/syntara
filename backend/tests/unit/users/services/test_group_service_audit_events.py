"""Tests for authz audit event emission from GroupsService membership ops.

Verifies that add_member / remove_member dispatch GroupMembershipEvent
domain events which become SECURITY_EVENT audit records (AAP-83643).
"""

# mypy: disable-error-code="attr-defined"

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.authz.audit.group_membership import GroupMembershipEvent, GroupMembershipHandler
from syntara.core.models import User
from syntara.core.models.group import Group
from syntara.users.services.group_service import GroupsService

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent


class TestGroupsServiceAddMemberAuditEvents:
    """Tests for audit event emission from GroupsService.add_member()."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({GroupMembershipEvent: GroupMembershipHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_add_member_emits_group_member_added_security_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Successful add_member should emit a group_member_added SECURITY_EVENT."""
        group_id = uuid4()
        user_id = uuid4()
        group = Group(id=group_id, name="developers", description="Devs", is_builtin=False, labels={})
        member = User(id=user_id, username="alice", email="alice@example.com", is_enabled=True)

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()

        # First exec: membership existence check -> None; insert path uses exec again
        not_member = Mock()
        not_member.one_or_none.return_value = None
        mock_session.exec = AsyncMock(return_value=not_member)

        service = GroupsService(session=mock_session, user=test_user)

        with (
            patch.object(service, "get_group_by_id", new_callable=AsyncMock, return_value=group),
            patch(
                "syntara.users.services.group_service.get_user_by_id",
                new_callable=AsyncMock,
                return_value=member,
            ),
        ):
            await service.add_member(group_id, user_id)

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "group_member_added"
        assert event.event_category == EventCategory.SECURITY_EVENT
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.authz"
        assert event.event_message == "Group member added: alice -> group developers"
        assert event.resource_urn == f"urn:syntara:group-membership:{group_id}:{user_id}"
        assert event.structured_data.data_type == "group-membership"
        assert event.structured_data.action == "added"
        assert event.structured_data.username == "alice"
        assert event.structured_data.group_name == "developers"
        assert event.structured_data.user_id == str(user_id)


class TestGroupsServiceRemoveMemberAuditEvents:
    """Tests for audit event emission from GroupsService.remove_member()."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({GroupMembershipEvent: GroupMembershipHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_remove_member_emits_group_member_removed_security_event(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Successful remove_member should emit a group_member_removed SECURITY_EVENT."""
        group_id = uuid4()
        user_id = uuid4()
        group = Group(id=group_id, name="developers", description="Devs", is_builtin=False, labels={})
        member = User(id=user_id, username="alice", email="alice@example.com", is_enabled=True)

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()

        is_member = Mock()
        is_member.one_or_none.return_value = user_id
        mock_session.exec = AsyncMock(return_value=is_member)

        service = GroupsService(session=mock_session, user=test_user)

        with (
            patch.object(service, "get_group_by_id", new_callable=AsyncMock, return_value=group),
            patch(
                "syntara.users.services.group_service.get_user_by_id",
                new_callable=AsyncMock,
                return_value=member,
            ),
            patch.object(service, "_guard_last_admin_removal", new_callable=AsyncMock),
        ):
            await service.remove_member(group_id, user_id)

        assert mock_do_emit.call_count == 1
        event: AuditEvent = mock_do_emit.call_args.args[0]

        assert event.event_action == "group_member_removed"
        assert event.event_category == EventCategory.SECURITY_EVENT
        assert event.event_severity == EventSeverity.INFO
        assert event.event_status == EventStatus.SUCCESS
        assert event.source_component == "syntara.authz"
        assert event.event_message == "Group member removed: alice -> group developers"
        assert event.structured_data.action == "removed"
        assert event.structured_data.user_id == str(user_id)


class TestGroupsServiceSetUserGroupsAuditEvents:
    """Tests for audit emission from set_user_groups membership diffs."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({GroupMembershipEvent: GroupMembershipHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_dispatch_membership_diff_emits_added_and_removed_events(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """Mixed add/remove diff should emit one SECURITY_EVENT per membership change."""
        user_id = uuid4()
        add_id = uuid4()
        remove_id = uuid4()

        name_rows = Mock()
        name_rows.all.return_value = [(add_id, "developers"), (remove_id, "auditors")]
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.exec = AsyncMock(return_value=name_rows)

        service = GroupsService(session=mock_session, user=test_user)
        await service._dispatch_membership_diff_events(
            user_id=user_id,
            username="alice",
            added={add_id},
            removed={remove_id},
        )

        assert mock_do_emit.call_count == 2
        actions = {call.args[0].event_action for call in mock_do_emit.call_args_list}
        assert actions == {"group_member_added", "group_member_removed"}
        for call in mock_do_emit.call_args_list:
            event: AuditEvent = call.args[0]
            assert event.event_category == EventCategory.SECURITY_EVENT
            assert event.source_component == "syntara.authz"
            assert event.structured_data.username == "alice"
            assert event.structured_data.user_id == str(user_id)

        by_action = {c.args[0].event_action: c.args[0] for c in mock_do_emit.call_args_list}
        assert by_action["group_member_added"].structured_data.group_name == "developers"
        assert by_action["group_member_removed"].structured_data.group_name == "auditors"

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_set_user_groups_invokes_diff_dispatch_after_commit(
        self,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """set_user_groups must dispatch membership events for the computed diff."""
        user_id = uuid4()
        auth_group_id = uuid4()
        current_group_id = uuid4()
        desired_group_id = uuid4()
        member = User(id=user_id, username="alice", email="alice@example.com", is_enabled=True)

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()

        # Sequence: auth group id, desired groups found, current memberships, delete, insert
        auth_result = Mock()
        auth_result.first.return_value = auth_group_id
        found_result = Mock()
        found_result.all.return_value = [auth_group_id, desired_group_id]
        current_result = Mock()
        current_result.all.return_value = [auth_group_id, current_group_id]
        write_result = Mock()

        mock_session.exec = AsyncMock(
            side_effect=[auth_result, found_result, current_result, write_result, write_result]
        )

        service = GroupsService(session=mock_session, user=test_user)
        with (
            patch(
                "syntara.users.services.group_service.get_user_by_id",
                new_callable=AsyncMock,
                return_value=member,
            ),
            patch.object(service, "_guard_last_admin_removal", new_callable=AsyncMock),
            patch.object(
                service,
                "_dispatch_membership_diff_events",
                new_callable=AsyncMock,
            ) as mock_dispatch,
            patch.object(
                service,
                "list_user_groups",
                new_callable=AsyncMock,
                return_value=Mock(),
            ),
        ):
            await service.set_user_groups(user_id, [desired_group_id])

        mock_dispatch.assert_awaited_once()
        assert mock_dispatch.await_args is not None
        kwargs = mock_dispatch.await_args.kwargs
        assert kwargs["user_id"] == user_id
        assert kwargs["username"] == "alice"
        assert kwargs["added"] == {desired_group_id}
        assert kwargs["removed"] == {current_group_id}
        assert mock_do_emit.call_count == 0  # dispatch helper mocked; emission tested above
