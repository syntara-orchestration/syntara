"""Route-level audit regression for POST /groups/{id}/members (AAP-83643).

Exercises the decorated add_member endpoint so both the domain event and the
@audit FunctionExecutionEvent are observed — including request.user_id capture.
"""

# mypy: disable-error-code="attr-defined"

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.events.function_execution import FunctionExecutionEvent, FunctionExecutionHandler
from syntara.audit.models.audit_event import EventCategory
from syntara.authz.audit.group_membership import GroupMembershipEvent, GroupMembershipHandler
from syntara.core.models import User
from syntara.core.models.group import Group, GroupMemberAdd
from syntara.users.groups_router import add_member
from syntara.users.services.group_service import GroupsService

if TYPE_CHECKING:
    from syntara.audit.models.audit_event import AuditEvent


class TestAddMemberRouteAuditEvents:
    """add_member route must emit SECURITY_EVENT domain + decorator audits with user_id."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register(
            {
                GroupMembershipEvent: GroupMembershipHandler(),
                FunctionExecutionEvent: FunctionExecutionHandler(),
            }
        )

    @pytest.mark.asyncio
    @patch("syntara.audit.emitter._do_emit_audit_event")
    @patch("syntara.users.groups_router.create_session_store")
    async def test_add_member_route_emits_security_events_with_target_user_id(
        self,
        mock_create_store: Mock,
        mock_do_emit: AsyncMock,
        test_user: User,
    ) -> None:
        """POST add_member path emits group_member_added + group_member_add SECURITY_EVENTs."""
        group_id = uuid4()
        user_id = uuid4()
        group = Group(id=group_id, name="developers", description="Devs", is_builtin=False, labels={})
        member = User(id=user_id, username="alice", email="alice@example.com", is_enabled=True)

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        not_member = Mock()
        not_member.one_or_none.return_value = None
        mock_session.exec = AsyncMock(return_value=not_member)

        store = AsyncMock()
        store.increment_token_version = AsyncMock()
        mock_create_store.return_value = store

        service = GroupsService(session=mock_session, user=test_user)
        db = AsyncMock(spec=AsyncSession)
        db.commit = AsyncMock()

        with (
            patch.object(service, "get_group_by_id", new_callable=AsyncMock, return_value=group),
            patch(
                "syntara.users.services.group_service.get_user_by_id",
                new_callable=AsyncMock,
                return_value=member,
            ),
        ):
            await add_member(
                group_id,
                GroupMemberAdd(user_id=user_id),
                service,
                db,
            )

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        by_action = {event.event_action: event for event in events}

        assert "group_member_added" in by_action
        assert "group_member_add" in by_action

        domain = by_action["group_member_added"]
        assert domain.event_category == EventCategory.SECURITY_EVENT
        assert domain.structured_data.user_id == str(user_id)
        assert domain.source_component == "syntara.authz"

        decorator = by_action["group_member_add"]
        assert decorator.event_category == EventCategory.SECURITY_EVENT
        function_args = decorator.structured_data.function_args
        assert function_args["group_id"] == group_id or str(function_args["group_id"]) == str(group_id)
        request_arg = function_args["request"]
        if isinstance(request_arg, dict):
            assert str(request_arg["user_id"]) == str(user_id)
        else:
            assert str(request_arg.user_id) == str(user_id)
