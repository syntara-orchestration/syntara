"""Unit tests for UserLoginHandler audit event mapping."""

from uuid import uuid4

from syntara.audit.models.audit_event import (
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.auth.audit.user_login import AMR, UserLoginEvent, UserLoginHandler
from syntara.core.models.principal import PrincipalType


class TestUserLoginHandler:
    """Test that UserLoginHandler produces correct AuditEvents."""

    def test_audit_event_fields_password(self) -> None:
        user_id = uuid4()
        event = UserLoginEvent(user_id=user_id, username="alice", amr=[AMR.PASSWORD], idp="local")
        audit = UserLoginHandler().handle(event)

        assert audit is not None
        assert audit.event_action == "user_login"
        assert audit.event_category == EventCategory.USER_ACTION
        assert audit.event_severity == EventSeverity.INFO
        assert audit.event_status == EventStatus.SUCCESS
        assert audit.actor_id == user_id
        assert audit.actor_type == PrincipalType.USER
        assert audit.actor_username == "alice"
        assert audit.source_component == "syntara.auth.login"
        assert "local" in audit.event_message
        assert audit.resource_urn == "urn:syntara:user:alice"
        assert audit.resource_name == "alice"

    def test_audit_event_fields_oidc(self) -> None:
        user_id = uuid4()
        event = UserLoginEvent(user_id=user_id, username="bob", amr=[AMR.FEDERATED], idp="okta")
        audit = UserLoginHandler().handle(event)

        assert audit is not None
        assert audit.event_action == "user_login"
        assert "okta" in audit.event_message
        assert audit.actor_id == user_id
        assert audit.actor_username == "bob"

    def test_first_login_produces_new_user_login_action(self) -> None:
        user_id = uuid4()
        event = UserLoginEvent(user_id=user_id, amr=[AMR.PASSWORD], idp="local", is_first_login=True)
        audit = UserLoginHandler().handle(event)

        assert audit is not None
        assert audit.event_action == "new_user_login"
        assert "First login" in audit.event_message

    def test_structured_data_contains_amr_and_idp(self) -> None:
        event = UserLoginEvent(user_id=uuid4(), amr=[AMR.FEDERATED], idp="okta")
        audit = UserLoginHandler().handle(event)

        assert audit is not None
        assert audit.structured_data is not None
        data = audit.structured_data.model_dump()
        assert data["amr"] == ["fed"]
        assert data["idp"] == "okta"
        assert data["is_first_login"] is False

    def test_structured_data_is_first_login_true(self) -> None:
        event = UserLoginEvent(user_id=uuid4(), amr=[AMR.PASSWORD], idp="local", is_first_login=True)
        audit = UserLoginHandler().handle(event)

        assert audit is not None
        data = audit.structured_data.model_dump()
        assert data["is_first_login"] is True

    def test_login_with_no_username(self) -> None:
        """Login with no username → resource_urn and resource_name are None."""
        user_id = uuid4()
        event = UserLoginEvent(user_id=user_id, username=None, amr=[AMR.PASSWORD], idp="local")
        audit = UserLoginHandler().handle(event)

        assert audit is not None
        assert audit.actor_username is None
        assert audit.resource_urn is None
        assert audit.resource_name is None
