"""Unit tests for session revocation audit events and handler."""

from syntara.audit.models.audit_event import (
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.auth.audit.session_revocation import (
    SessionRevocationEvent,
    SessionRevocationHandler,
)
from syntara.core.models.principal import PrincipalType


class TestSessionRevocationHandler:
    """Tests for SessionRevocationHandler."""

    def test_produces_critical_security_event_for_user(self) -> None:
        """Should produce a CRITICAL SECURITY_EVENT audit event for user revocation."""
        event = SessionRevocationEvent(
            actor_username="admin-cli",
            actor_source="cli",
            target_type="user",
            target_identifier="alice",
            sessions_revoked=3,
        )
        handler = SessionRevocationHandler()
        audit_event = handler.handle(event)

        assert audit_event.event_category == EventCategory.SECURITY_EVENT
        assert audit_event.event_severity == EventSeverity.CRITICAL
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.event_action == "session_revocation"
        assert audit_event.actor_type == PrincipalType.USER
        assert audit_event.actor_username == "admin-cli"
        assert "3 session(s)" in audit_event.event_message
        assert "user" in audit_event.event_message
        assert "alice" in audit_event.event_message
        assert "admin-cli" in audit_event.event_message
        assert "cli" in audit_event.event_message

    def test_produces_critical_security_event_for_idp(self) -> None:
        """Should produce a CRITICAL SECURITY_EVENT audit event for IdP revocation."""
        event = SessionRevocationEvent(
            actor_username="ops-admin",
            actor_source="cli",
            target_type="idp",
            target_identifier="Corporate Okta",
            sessions_revoked=12,
        )
        handler = SessionRevocationHandler()
        audit_event = handler.handle(event)

        assert audit_event.event_category == EventCategory.SECURITY_EVENT
        assert audit_event.event_severity == EventSeverity.CRITICAL
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.event_action == "session_revocation"
        assert audit_event.actor_username == "ops-admin"
        assert "12 session(s)" in audit_event.event_message
        assert "idp" in audit_event.event_message
        assert "Corporate Okta" in audit_event.event_message

    def test_structured_data_contains_revocation_info(self) -> None:
        """Should include target type, identifier, and count in structured data."""
        event = SessionRevocationEvent(
            actor_username="admin-cli",
            actor_source="cli",
            target_type="user",
            target_identifier="bob",
            sessions_revoked=1,
        )
        handler = SessionRevocationHandler()
        audit_event = handler.handle(event)
        data = audit_event.structured_data

        assert data.data_type == "session-revocation"
        assert data.target_type == "user"  # type: ignore[attr-defined]
        assert data.target_identifier == "bob"  # type: ignore[attr-defined]
        assert data.sessions_revoked == 1  # type: ignore[attr-defined]
        assert data.actor_source == "cli"  # type: ignore[attr-defined]

    def test_zero_sessions_revoked(self) -> None:
        """Should handle zero sessions gracefully."""
        event = SessionRevocationEvent(
            actor_username="admin-cli",
            actor_source="cli",
            target_type="idp",
            target_identifier="Unused Provider",
            sessions_revoked=0,
        )
        handler = SessionRevocationHandler()
        audit_event = handler.handle(event)

        assert "0 session(s)" in audit_event.event_message
        assert audit_event.structured_data.sessions_revoked == 0  # type: ignore[attr-defined]

    def test_source_component(self) -> None:
        """Should use the auth revocation source component."""
        event = SessionRevocationEvent(
            actor_username="admin-cli",
            actor_source="cli",
            target_type="user",
            target_identifier="alice",
            sessions_revoked=1,
        )
        handler = SessionRevocationHandler()
        audit_event = handler.handle(event)

        assert audit_event.source_component == "syntara.auth.revocation"

    def test_resource_fields_for_user_target(self) -> None:
        """Resource fields should use user URN pattern for user targets."""
        event = SessionRevocationEvent(
            actor_username="admin-cli",
            actor_source="cli",
            target_type="user",
            target_identifier="alice",
            sessions_revoked=3,
        )
        handler = SessionRevocationHandler()
        audit_event = handler.handle(event)

        assert audit_event.resource_urn == "urn:syntara:user:alice"
        assert audit_event.resource_name == "alice"

    def test_resource_fields_for_idp_target(self) -> None:
        """Resource fields should use identity_provider URN pattern for IdP targets."""
        event = SessionRevocationEvent(
            actor_username="ops-admin",
            actor_source="cli",
            target_type="idp",
            target_identifier="Corporate Okta",
            sessions_revoked=12,
        )
        handler = SessionRevocationHandler()
        audit_event = handler.handle(event)

        # URL-encoded to comply with RFC 8141 (spaces become %20)
        assert audit_event.resource_urn == "urn:syntara:identity_provider:Corporate%20Okta"
        assert audit_event.resource_name == "Corporate Okta"

    def test_resource_fields_for_unknown_target_type(self) -> None:
        """Resource fields should use generic URN pattern for unknown target types."""
        event = SessionRevocationEvent(
            actor_username="admin-cli",
            actor_source="cli",
            target_type="unknown_type",
            target_identifier="test_target",
            sessions_revoked=1,
        )
        handler = SessionRevocationHandler()
        audit_event = handler.handle(event)

        assert audit_event.resource_urn == "urn:syntara:unknown_type:test_target"
        assert audit_event.resource_name == "test_target"
