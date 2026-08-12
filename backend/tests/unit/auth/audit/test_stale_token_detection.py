"""Unit tests for stale token detection audit events and handlers."""

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.auth.audit.stale_token_detection import (
    StaleTokenDetectionEvent,
    StaleTokenDetectionHandler,
)
from syntara.core.models.principal import PrincipalType


class TestStaleTokenDetectionHandler:
    """Tests for StaleTokenDetectionHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(StaleTokenDetectionHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        user_id = str(uuid4())
        event = StaleTokenDetectionEvent(
            user_id=user_id,
            token_version=5,
            current_version=10,
        )
        handler = StaleTokenDetectionHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "stale_token_detected"
        assert result.source_component == "syntara.auth.middleware"
        assert result.actor_type == PrincipalType.USER

    def test_resource_fields(self) -> None:
        user_id = str(uuid4())
        event = StaleTokenDetectionEvent(
            user_id=user_id,
            token_version=5,
            current_version=10,
        )
        handler = StaleTokenDetectionHandler()
        result = handler.handle(event)

        assert result.resource_urn == f"urn:syntara:user:{user_id}"
        assert result.resource_name == user_id

    def test_resource_name_uses_user_name_when_provided(self) -> None:
        user_id = str(uuid4())
        user_name = "testuser@example.com"
        event = StaleTokenDetectionEvent(
            user_id=user_id,
            token_version=5,
            current_version=10,
            user_name=user_name,
        )
        handler = StaleTokenDetectionHandler()
        result = handler.handle(event)

        assert result.resource_urn == f"urn:syntara:user:{user_id}"
        assert result.resource_name == user_name

    def test_resource_name_falls_back_to_user_id_when_user_name_none(self) -> None:
        user_id = str(uuid4())
        event = StaleTokenDetectionEvent(
            user_id=user_id,
            token_version=5,
            current_version=10,
            user_name=None,
        )
        handler = StaleTokenDetectionHandler()
        result = handler.handle(event)

        assert result.resource_urn == f"urn:syntara:user:{user_id}"
        assert result.resource_name == user_id

    def test_resource_fields_with_invalid_uuid(self) -> None:
        # Test with a user_id that's not a valid UUID
        user_id = "invalid-uuid-string"
        event = StaleTokenDetectionEvent(
            user_id=user_id,
            token_version=5,
            current_version=10,
        )
        handler = StaleTokenDetectionHandler()
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
        event = StaleTokenDetectionEvent(
            user_id=user_id,
            token_version=5,
            current_version=10,
            user_name=user_name,
        )
        handler = StaleTokenDetectionHandler()
        result = handler.handle(event)

        assert result.resource_urn == f"urn:syntara:user:{user_id}"
        assert result.resource_name == user_name
        assert result.actor_id is None

    def test_structured_data(self) -> None:
        user_id = str(uuid4())
        event = StaleTokenDetectionEvent(
            user_id=user_id,
            token_version=5,
            current_version=10,
        )
        handler = StaleTokenDetectionHandler()
        result = handler.handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "stale-token-detection"
        assert result.structured_data.token_version == 5  # type: ignore[attr-defined]
        assert result.structured_data.current_version == 10  # type: ignore[attr-defined]
