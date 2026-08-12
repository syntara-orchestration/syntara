"""Unit tests for group membership domain audit events and handlers."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.authz.audit.group_membership import (
    GroupMembershipEvent,
    GroupMembershipHandler,
)


class TestGroupMembershipEvent:
    """Tests for GroupMembershipEvent dataclass."""

    def test_construction_defaults(self) -> None:
        user_id = uuid4()
        group_id = uuid4()
        event = GroupMembershipEvent(
            user_id=user_id,
            username="alice",
            group_id=group_id,
            group_name="developers",
            action="added",
        )
        assert event.user_id == user_id
        assert event.username == "alice"
        assert event.group_id == group_id
        assert event.group_name == "developers"
        assert event.action == "added"
        assert event.error_type is None


class TestGroupMembershipHandler:
    """Tests for GroupMembershipHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(GroupMembershipHandler, AuditEventHandler)

    def test_group_member_added_is_security_event(self) -> None:
        """Added action -> SECURITY_EVENT, INFO, SUCCESS with user identity."""
        user_id = uuid4()
        group_id = uuid4()
        event = GroupMembershipEvent(
            user_id=user_id,
            username="alice",
            group_id=group_id,
            group_name="developers",
            action="added",
        )
        handler = GroupMembershipHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "group_member_added"
        assert result.source_component == "syntara.authz"
        assert result.event_message == "Group member added: alice -> group developers"
        assert result.resource_urn == f"urn:syntara:group-membership:{group_id}:{user_id}"
        assert result.resource_name == "developers"

        assert result.structured_data.data_type == "group-membership"
        assert result.structured_data.action == "added"
        assert result.structured_data.username == "alice"
        assert result.structured_data.group_name == "developers"
        assert result.structured_data.user_id == str(user_id)
        assert result.structured_data.group_id == str(group_id)

    def test_group_member_removed_is_security_event(self) -> None:
        """Removed action -> SECURITY_EVENT with group_member_removed action."""
        user_id = uuid4()
        group_id = uuid4()
        event = GroupMembershipEvent(
            user_id=user_id,
            username="bob",
            group_id=group_id,
            group_name="auditors",
            action="removed",
        )
        handler = GroupMembershipHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_action == "group_member_removed"
        assert result.event_message == "Group member removed: bob -> group auditors"
        assert result.structured_data.action == "removed"

    def test_error_sets_error_severity(self) -> None:
        event = GroupMembershipEvent(
            user_id=uuid4(),
            username="alice",
            group_id=uuid4(),
            group_name="developers",
            action="added",
            error_type="IntegrityError",
        )
        result = GroupMembershipHandler().handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.structured_data.error_type == "IntegrityError"
