"""Unit tests for disabled user rejection audit events and handlers."""

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.auth.audit.disabled_user_rejection import (
    DisabledUserRejectionEvent,
    DisabledUserRejectionHandler,
    RejectionContext,
)
from syntara.core.models.principal import PrincipalType


class TestDisabledUserRejectionHandler:
    """Tests for DisabledUserRejectionHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(DisabledUserRejectionHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        user_id = str(uuid4())
        event = DisabledUserRejectionEvent(
            user_id=user_id,
            context=RejectionContext.MIDDLEWARE,
        )
        handler = DisabledUserRejectionHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "disabled_user_rejected"
        assert result.source_component == "syntara.auth.middleware"
        assert "middleware" in result.event_message
        assert result.actor_type == PrincipalType.USER

    def test_maps_token_refresh_context(self) -> None:
        user_id = str(uuid4())
        event = DisabledUserRejectionEvent(
            user_id=user_id,
            context=RejectionContext.TOKEN_REFRESH,
        )
        handler = DisabledUserRejectionHandler()
        result = handler.handle(event)

        assert result.source_component == "syntara.auth.token_refresh"
        assert "token_refresh" in result.event_message

    def test_resource_fields(self) -> None:
        user_id = str(uuid4())
        event = DisabledUserRejectionEvent(
            user_id=user_id,
            context=RejectionContext.MIDDLEWARE,
        )
        handler = DisabledUserRejectionHandler()
        result = handler.handle(event)

        assert result.resource_urn == f"urn:syntara:user:{user_id}"
        assert result.resource_name == user_id

    def test_resource_name_uses_user_name_when_provided(self) -> None:
        user_id = str(uuid4())
        user_name = "testuser@example.com"
        event = DisabledUserRejectionEvent(
            user_id=user_id,
            context=RejectionContext.MIDDLEWARE,
            user_name=user_name,
        )
        handler = DisabledUserRejectionHandler()
        result = handler.handle(event)

        assert result.resource_urn == f"urn:syntara:user:{user_id}"
        assert result.resource_name == user_name

    def test_resource_name_falls_back_to_user_id_when_user_name_none(self) -> None:
        user_id = str(uuid4())
        event = DisabledUserRejectionEvent(
            user_id=user_id,
            context=RejectionContext.MIDDLEWARE,
            user_name=None,
        )
        handler = DisabledUserRejectionHandler()
        result = handler.handle(event)

        assert result.resource_urn == f"urn:syntara:user:{user_id}"
        assert result.resource_name == user_id

    def test_resource_fields_with_invalid_uuid(self) -> None:
        # Test with a user_id that's not a valid UUID
        user_id = "invalid-uuid-string"
        event = DisabledUserRejectionEvent(
            user_id=user_id,
            context=RejectionContext.MIDDLEWARE,
        )
        handler = DisabledUserRejectionHandler()
        result = handler.handle(event)

        # Should still set resource fields even if user_id is not a valid UUID
        assert result.resource_urn == f"urn:syntara:user:{user_id}"
        assert result.resource_name == user_id
        # actor_id should be None for invalid UUID
        assert result.actor_id is None

    def test_resource_name_with_user_name_and_invalid_uuid(self) -> None:
        # Even with invalid UUID, should use user_name when provided
        user_id = "invalid-uuid-string"
        user_name = "testuser@example.com"
        event = DisabledUserRejectionEvent(
            user_id=user_id,
            context=RejectionContext.MIDDLEWARE,
            user_name=user_name,
        )
        handler = DisabledUserRejectionHandler()
        result = handler.handle(event)

        assert result.resource_urn == f"urn:syntara:user:{user_id}"
        assert result.resource_name == user_name
        assert result.actor_id is None

    def test_structured_data(self) -> None:
        user_id = str(uuid4())
        event = DisabledUserRejectionEvent(
            user_id=user_id,
            context=RejectionContext.MIDDLEWARE,
        )
        handler = DisabledUserRejectionHandler()
        result = handler.handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "disabled-user-rejection"
        assert result.structured_data.context == RejectionContext.MIDDLEWARE  # type: ignore[attr-defined]
