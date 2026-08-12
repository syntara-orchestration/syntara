"""Unit tests for OIDCFlowEvent and OIDCFlowHandler."""

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.auth.audit.oidc_flow import OIDCFlowEvent, OIDCFlowHandler, OIDCStage
from syntara.core.models.principal import PrincipalType


class TestOIDCFlowEvent:
    """Tests for OIDCFlowEvent dataclass."""

    def test_minimal_construction_defaults(self) -> None:
        """OIDCFlowEvent can be constructed with just provider_id and stage; all optionals default."""
        event = OIDCFlowEvent(provider_id=None, stage=OIDCStage.AUTHORIZE)
        assert event.provider_id is None
        assert event.stage == OIDCStage.AUTHORIZE
        assert event.user_id is None
        assert event.username is None
        assert event.error_type is None


class TestOIDCFlowHandler:
    """Tests for OIDCFlowHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """OIDCFlowHandler is a subclass of AuditEventHandler."""
        assert issubclass(OIDCFlowHandler, AuditEventHandler)

    def test_successful_authorize(self) -> None:
        """Successful authorize → USER_ACTION / INFO / SUCCESS / 'oidc_authorize' / SYSTEM actor."""
        event = OIDCFlowEvent(provider_id=None, stage=OIDCStage.AUTHORIZE)
        handler = OIDCFlowHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "oidc_authorize"
        assert result.actor_type == PrincipalType.SYSTEM
        assert result.actor_id is None
        assert result.actor_username is None
        assert result.source_component == "syntara.auth.oidc"

    def test_successful_callback_with_user(self) -> None:
        """Successful callback with user → actor_id=user_id, actor_name=username, actor_type=USER, 'oidc_callback'."""
        uid = uuid4()
        event = OIDCFlowEvent(provider_id=None, stage=OIDCStage.CALLBACK, user_id=uid, username="testuser")
        handler = OIDCFlowHandler()
        result = handler.handle(event)

        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "oidc_callback"
        assert result.actor_type == PrincipalType.USER
        assert result.actor_id == uid
        assert result.actor_username == "testuser"

    def test_error_produces_security_event_error_severity(self) -> None:
        """Error → SECURITY_EVENT / ERROR severity / ERROR status / 'oidc_callback'."""
        event = OIDCFlowEvent(
            provider_id=None,
            stage=OIDCStage.CALLBACK,
            error_type="JWTDecodeError",
        )
        handler = OIDCFlowHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "oidc_callback"

    def test_authorize_error_produces_error_severity(self) -> None:
        """Error in authorize stage → SECURITY_EVENT / ERROR severity / 'oidc_authorize'."""
        event = OIDCFlowEvent(
            provider_id=None,
            stage=OIDCStage.AUTHORIZE,
            error_type="ProviderNotFound",
        )
        handler = OIDCFlowHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "oidc_authorize"

    def test_provider_id_uuid_is_stringified_in_structured_data(self) -> None:
        """provider_id UUID is stringified in structured data."""
        pid = uuid4()
        event = OIDCFlowEvent(provider_id=pid, stage=OIDCStage.AUTHORIZE)
        handler = OIDCFlowHandler()
        result = handler.handle(event)

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "oidc-context"
        assert result.structured_data.provider_id == str(pid)  # type: ignore[attr-defined]

    def test_none_provider_id_stays_none_in_structured_data(self) -> None:
        """None provider_id stays None in structured data."""
        event = OIDCFlowEvent(provider_id=None, stage=OIDCStage.AUTHORIZE)
        handler = OIDCFlowHandler()
        result = handler.handle(event)

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.provider_id is None  # type: ignore[attr-defined]

    def test_resource_fields_with_username(self) -> None:
        """Resource fields use username when available."""
        uid = uuid4()
        event = OIDCFlowEvent(provider_id=None, stage=OIDCStage.CALLBACK, user_id=uid, username="testuser")
        handler = OIDCFlowHandler()
        result = handler.handle(event)

        assert result.resource_urn == "urn:syntara:user:testuser"
        assert result.resource_name == "testuser"

    def test_resource_fields_fallback_to_user_id(self) -> None:
        """Resource fields fall back to user_id when username is None."""
        uid = uuid4()
        event = OIDCFlowEvent(provider_id=None, stage=OIDCStage.CALLBACK, user_id=uid, username=None)
        handler = OIDCFlowHandler()
        result = handler.handle(event)

        assert result.resource_urn == f"urn:syntara:user:{uid}"
        assert result.resource_name == str(uid)

    def test_resource_fields_none_when_both_missing(self) -> None:
        """Resource fields are None when both username and user_id are None."""
        event = OIDCFlowEvent(provider_id=None, stage=OIDCStage.AUTHORIZE, user_id=None, username=None)
        handler = OIDCFlowHandler()
        result = handler.handle(event)

        assert result.resource_urn is None
        assert result.resource_name is None
