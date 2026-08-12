"""Unit tests for AuthorizationDeniedEvent/Handler."""

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.authz.audit.authorization_denied import (
    AuthorizationDeniedEvent,
    AuthorizationDeniedHandler,
)
from syntara.core.models.principal import PrincipalType


class TestAuthorizationDeniedHandler:
    """Tests for AuthorizationDeniedHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(AuthorizationDeniedHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        user_id = uuid4()
        event = AuthorizationDeniedEvent(
            user_id=user_id,
            username="alice",
            resource_id="123",
            resource_type="workflow",
            resource_name="my-workflow",
            action="execute",
            denied_by="policy:require-approval",
        )
        handler = AuthorizationDeniedHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "authorization_denied"
        assert result.actor_type == PrincipalType.USER
        assert result.actor_id == user_id
        assert result.actor_username == "alice"
        assert result.source_component == "syntara.authz"
        assert "execute" in result.event_message
        assert "workflow" in result.event_message
        assert result.resource_urn == "urn:syntara:workflow:123"
        assert result.resource_name == "my-workflow"

    def test_structured_data(self) -> None:
        user_id = uuid4()
        event = AuthorizationDeniedEvent(
            user_id=user_id,
            username="bob",
            resource_id="123",
            resource_type="credential",
            resource_name="my-credential",
            action="delete",
            denied_by="rbac:insufficient-permissions",
        )
        handler = AuthorizationDeniedHandler()
        result = handler.handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "authorization-denied"
        assert result.structured_data.resource_type == "credential"  # type: ignore[attr-defined]
        assert result.structured_data.action == "delete"  # type: ignore[attr-defined]
        assert result.structured_data.denied_by == "rbac:insufficient-permissions"  # type: ignore[attr-defined]

    def test_denied_by_optional(self) -> None:
        user_id = uuid4()
        event = AuthorizationDeniedEvent(
            user_id=user_id,
            username="charlie",
            resource_id="123",
            resource_type="project",
            resource_name="my-project",
            action="read",
        )
        handler = AuthorizationDeniedHandler()
        result = handler.handle(event)

        assert result.structured_data is not None
        assert result.structured_data.denied_by is None  # type: ignore[attr-defined]
        assert result.resource_urn == "urn:syntara:project:123"
        assert result.resource_name == "my-project"
