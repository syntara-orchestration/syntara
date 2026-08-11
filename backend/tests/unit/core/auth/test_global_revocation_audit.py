"""Unit tests for global revocation audit events and handlers."""

from uuid import uuid4

from syntara.audit.models.audit_event import (
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.auth.audit.global_revocation import (
    GlobalRevocationEvent,
    GlobalRevocationHandler,
    GlobalRevocationRejectEvent,
    GlobalRevocationRejectHandler,
)
from syntara.core.models.principal import PrincipalType


class TestGlobalRevocationHandler:
    """Tests for GlobalRevocationHandler."""

    def test_produces_critical_security_event(self) -> None:
        """Should produce a CRITICAL SECURITY_EVENT audit event."""
        event = GlobalRevocationEvent(
            actor_username="admin-cli",
            actor_source="cli",
            revocation_timestamp="2025-01-15T10:30:00+00:00",
        )
        handler = GlobalRevocationHandler()
        audit_event = handler.handle(event)

        assert audit_event.event_category == EventCategory.SECURITY_EVENT
        assert audit_event.event_severity == EventSeverity.CRITICAL
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.event_action == "global_token_revocation"
        assert audit_event.actor_type == PrincipalType.USER
        assert audit_event.actor_username == "admin-cli"
        assert "admin-cli" in audit_event.event_message
        assert "cli" in audit_event.event_message
        assert "2025-01-15T10:30:00+00:00" in audit_event.event_message

    def test_structured_data_contains_revocation_info(self) -> None:
        """Should include revocation timestamp and actor source in structured data."""
        event = GlobalRevocationEvent(
            actor_username="ops-admin",
            actor_source="cli",
            revocation_timestamp="2025-06-01T00:00:00+00:00",
        )
        handler = GlobalRevocationHandler()
        audit_event = handler.handle(event)
        data = audit_event.structured_data

        assert data.data_type == "global-revocation"
        assert data.revocation_timestamp == "2025-06-01T00:00:00+00:00"  # type: ignore[attr-defined]
        assert data.actor_source == "cli"  # type: ignore[attr-defined]


class TestGlobalRevocationRejectHandler:
    """Tests for GlobalRevocationRejectHandler."""

    def test_produces_warning_security_event(self) -> None:
        """Should produce a WARNING SECURITY_EVENT audit event."""
        user_id = uuid4()
        event = GlobalRevocationRejectEvent(
            user_id=user_id,
            username="alice",
            token_issued_at="2025-01-14T09:00:00+00:00",  # noqa: S106
            revocation_timestamp="2025-01-15T10:30:00+00:00",
            token_type="access",  # noqa: S106
        )
        handler = GlobalRevocationRejectHandler()
        audit_event = handler.handle(event)

        assert audit_event.event_category == EventCategory.SECURITY_EVENT
        assert audit_event.event_severity == EventSeverity.WARNING
        assert audit_event.event_status == EventStatus.ERROR
        assert audit_event.event_action == "globally_revoked_token_rejected"
        assert audit_event.actor_id == user_id
        assert audit_event.actor_username == "alice"
        assert "access" in audit_event.event_message
        assert "alice" in audit_event.event_message

    def test_handles_refresh_token_type(self) -> None:
        """Should include the correct token type in the message."""
        event = GlobalRevocationRejectEvent(
            user_id=None,
            username="bob",
            token_issued_at="2025-01-14T09:00:00+00:00",  # noqa: S106
            revocation_timestamp="2025-01-15T10:30:00+00:00",
            token_type="refresh",  # noqa: S106
        )
        handler = GlobalRevocationRejectHandler()
        audit_event = handler.handle(event)

        assert "refresh" in audit_event.event_message
        assert audit_event.structured_data.token_type == "refresh"  # type: ignore[attr-defined]  # noqa: S105

    def test_handles_unknown_username(self) -> None:
        """Should handle None username gracefully."""
        event = GlobalRevocationRejectEvent(
            user_id=None,
            username=None,
            token_issued_at="2025-01-14T09:00:00+00:00",  # noqa: S106
            revocation_timestamp="2025-01-15T10:30:00+00:00",
        )
        handler = GlobalRevocationRejectHandler()
        audit_event = handler.handle(event)

        assert "unknown" in audit_event.event_message
        assert audit_event.actor_username is None
