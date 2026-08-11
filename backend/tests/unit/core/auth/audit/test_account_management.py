"""Unit tests for AccountEnableEvent/Handler and PasswordResetEvent/Handler."""

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.auth.audit.account_management import (
    AccountEnableEvent,
    AccountEnableHandler,
    PasswordResetEvent,
    PasswordResetHandler,
)
from syntara.core.models.principal import PrincipalType


class TestAccountEnableHandler:
    """Tests for AccountEnableHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(AccountEnableHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        event = AccountEnableEvent(
            actor_username="ops@corp.com",
            actor_source="cli",
            target_username="alice",
            sessions_revoked=2,
        )
        handler = AccountEnableHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "account_enable"
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == "ops@corp.com"
        assert result.source_component == "syntara.auth.account_management"
        assert "alice" in result.event_message
        assert "ops@corp.com" in result.event_message
        assert result.resource_urn == "urn:syntara:user:alice"
        assert result.resource_name == "alice"

    def test_structured_data(self) -> None:
        event = AccountEnableEvent(
            actor_username="admin-cli",
            actor_source="cli",
            target_username="bob",
            sessions_revoked=0,
        )
        handler = AccountEnableHandler()
        result = handler.handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "account-enable"
        assert result.structured_data.target_username == "bob"  # type: ignore[attr-defined]
        assert result.structured_data.sessions_revoked == 0  # type: ignore[attr-defined]
        assert result.structured_data.actor_source == "cli"  # type: ignore[attr-defined]


class TestPasswordResetHandler:
    """Tests for PasswordResetHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(PasswordResetHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        event = PasswordResetEvent(
            actor_username="security-team@corp.com",
            actor_source="cli",
            target_username="charlie",
            sessions_revoked=5,
        )
        handler = PasswordResetHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.CRITICAL
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "password_reset"
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == "security-team@corp.com"
        assert result.source_component == "syntara.auth.account_management"
        assert "charlie" in result.event_message
        assert "security-team@corp.com" in result.event_message
        assert result.resource_urn == "urn:syntara:user:charlie"
        assert result.resource_name == "charlie"

    def test_structured_data(self) -> None:
        event = PasswordResetEvent(
            actor_username="admin-cli",
            actor_source="cli",
            target_username="dave",
            sessions_revoked=3,
        )
        handler = PasswordResetHandler()
        result = handler.handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "password-reset"
        assert result.structured_data.target_username == "dave"  # type: ignore[attr-defined]
        assert result.structured_data.sessions_revoked == 3  # type: ignore[attr-defined]
        assert result.structured_data.actor_source == "cli"  # type: ignore[attr-defined]
