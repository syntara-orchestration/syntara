"""Unit tests for UserPasswordChangedEvent/Handler and UserAccountStatusChangedEvent/Handler."""

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.auth.audit.user_account_change import (
    AccountStatus,
    UserAccountStatusChangedEvent,
    UserAccountStatusChangedHandler,
    UserPasswordChangedEvent,
    UserPasswordChangedHandler,
)
from syntara.core.models.principal import PrincipalType


class TestUserPasswordChangedHandler:
    """Tests for UserPasswordChangedHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(UserPasswordChangedHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        actor_id = uuid4()
        target_id = uuid4()
        event = UserPasswordChangedEvent(
            actor_id=actor_id,
            actor_username="admin",
            target_user_id=target_id,
            target_username="alice",
        )
        handler = UserPasswordChangedHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "password_changed"
        assert result.actor_type == PrincipalType.USER
        assert result.actor_id == actor_id
        assert result.actor_username == "admin"
        assert result.source_component == "syntara.auth.account_management"
        assert "alice" in result.event_message
        assert result.resource_urn == "urn:syntara:user:alice"
        assert result.resource_name == "alice"

    def test_structured_data(self) -> None:
        actor_id = uuid4()
        target_id = uuid4()
        event = UserPasswordChangedEvent(
            actor_id=actor_id,
            actor_username="admin",
            target_user_id=target_id,
            target_username="bob",
        )
        handler = UserPasswordChangedHandler()
        result = handler.handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "password-changed"
        assert result.structured_data.target_user_id == str(target_id)  # type: ignore[attr-defined]
        assert result.structured_data.target_username == "bob"  # type: ignore[attr-defined]


class TestUserAccountStatusChangedHandler:
    """Tests for UserAccountStatusChangedHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(UserAccountStatusChangedHandler, AuditEventHandler)

    def test_maps_event_to_audit_event_disabled(self) -> None:
        actor_id = uuid4()
        target_id = uuid4()
        event = UserAccountStatusChangedEvent(
            actor_id=actor_id,
            actor_username="admin",
            target_user_id=target_id,
            target_username="alice",
            new_status=AccountStatus.DISABLED,
        )
        handler = UserAccountStatusChangedHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "account_disabled"
        assert result.actor_type == PrincipalType.USER
        assert result.actor_id == actor_id
        assert result.actor_username == "admin"
        assert result.source_component == "syntara.auth.account_management"
        assert "alice" in result.event_message
        assert "disabled" in result.event_message
        assert result.resource_urn == "urn:syntara:user:alice"
        assert result.resource_name == "alice"

    def test_maps_event_to_audit_event_enabled(self) -> None:
        actor_id = uuid4()
        target_id = uuid4()
        event = UserAccountStatusChangedEvent(
            actor_id=actor_id,
            actor_username="admin",
            target_user_id=target_id,
            target_username="bob",
            new_status=AccountStatus.ENABLED,
        )
        handler = UserAccountStatusChangedHandler()
        result = handler.handle(event)

        assert result.event_action == "account_enabled"
        assert "enabled" in result.event_message
        assert result.resource_urn == "urn:syntara:user:bob"
        assert result.resource_name == "bob"

    def test_structured_data(self) -> None:
        actor_id = uuid4()
        target_id = uuid4()
        event = UserAccountStatusChangedEvent(
            actor_id=actor_id,
            actor_username="admin",
            target_user_id=target_id,
            target_username="charlie",
            new_status=AccountStatus.DISABLED,
        )
        handler = UserAccountStatusChangedHandler()
        result = handler.handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "account-status-changed"
        assert result.structured_data.target_user_id == str(target_id)  # type: ignore[attr-defined]
        assert result.structured_data.target_username == "charlie"  # type: ignore[attr-defined]
        assert result.structured_data.new_status == AccountStatus.DISABLED  # type: ignore[attr-defined]
