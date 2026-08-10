"""Tests that create_user emits GroupMembershipEvent for initial groups (AAP-83643)."""

# mypy: disable-error-code="attr-defined"

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import EventCategory
from syntara.authz.audit.group_membership import GroupMembershipEvent, GroupMembershipHandler
from syntara.authz.resolver import AUTHENTICATED_GROUP_NAME
from syntara.core.models import User
from syntara.core.models.group import Group
from syntara.users.services.user_service import UsersService

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent


class TestCreateUserMembershipAuditEvents:
    """Initial group grants on user create must emit SECURITY_EVENT membership audits."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({GroupMembershipEvent: GroupMembershipHandler()})

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    @patch("syntara.users.services.user_service.hash_password", return_value="hashed")
    async def test_create_user_with_group_names_emits_group_member_added_events(
        self,
        mock_hash: Mock,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """create_user assigning groups must emit group_member_added for each membership."""
        assert mock_hash.return_value == "hashed"
        auth_id = uuid4()
        dev_id = uuid4()
        auth_group = Group(id=auth_id, name=AUTHENTICATED_GROUP_NAME, description="auth", is_builtin=True, labels={})
        dev_group = Group(id=dev_id, name="developers", description="devs", is_builtin=False, labels={})

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        groups_result = Mock()
        groups_result.all.return_value = [auth_group, dev_group]
        mock_session.exec = AsyncMock(return_value=groups_result)

        service = UsersService(session=mock_session, user=test_user)

        plaintext = "fixture-only-value"
        with patch.object(service, "_commit_with_duplicate_check", new_callable=AsyncMock):
            created = await service.create_user(
                username="alice",
                first_name="Alice",
                password=plaintext,
                group_names=["developers"],
            )

        assert mock_do_emit.call_count == 2
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        assert all(event.event_action == "group_member_added" for event in events)
        assert all(event.event_category == EventCategory.SECURITY_EVENT for event in events)
        assert all(event.structured_data.username == "alice" for event in events)
        assert {event.structured_data.group_name for event in events} == {
            AUTHENTICATED_GROUP_NAME,
            "developers",
        }
        assert all(event.structured_data.user_id == str(created.id) for event in events)
