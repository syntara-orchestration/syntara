"""Unit tests for LoginAttemptEvent and LoginAttemptHandler."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.auth.audit.login_attempt import (
    LoginAttemptEvent,
    LoginAttemptHandler,
    LoginErrorReason,
    LoginMethod,
)
from syntara.core.models.principal import PrincipalType


class TestLoginAttemptEvent:
    """Tests for LoginAttemptEvent dataclass."""

    def test_minimal_construction_defaults(self) -> None:
        """LoginAttemptEvent can be constructed with just username and method; defaults apply."""
        event = LoginAttemptEvent(username="alice", method=LoginMethod.PASSWORD)
        assert event.username == "alice"
        assert event.method == LoginMethod.PASSWORD
        assert event.user_id is None
        assert event.error_type is None

    def test_enrichment_after_construction(self) -> None:
        """error_type and user_id can be set after construction."""
        event = LoginAttemptEvent(username="bob", method=LoginMethod.OIDC)
        uid = uuid4()
        event.error_type = "SomeError"
        event.user_id = uid
        assert event.error_type == "SomeError"
        assert event.user_id == uid

    def test_error_type_can_be_enum(self) -> None:
        """error_type can be set to LoginErrorReason enum."""
        event = LoginAttemptEvent(
            username="alice", method=LoginMethod.PASSWORD, error_type=LoginErrorReason.BAD_PASSWORD
        )
        assert event.error_type == LoginErrorReason.BAD_PASSWORD


class TestLoginAttemptHandler:
    """Tests for LoginAttemptHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """LoginAttemptHandler is a subclass of AuditEventHandler."""
        assert issubclass(LoginAttemptHandler, AuditEventHandler)

    def test_successful_password_login(self) -> None:
        """Successful login produces USER_ACTION / INFO / SUCCESS / 'login' event."""
        uid = uuid4()
        event = LoginAttemptEvent(username="alice", method=LoginMethod.PASSWORD, user_id=uid)
        handler = LoginAttemptHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "login"
        assert result.actor_id == uid
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == "alice"
        assert result.source_component == "syntara.auth.login"
        assert result.resource_urn == "urn:syntara:user:alice"
        assert result.resource_name == "alice"

    def test_failed_login_business_error_known_user(self) -> None:
        """Failed login with LoginErrorReason → SECURITY_EVENT / WARNING / ERROR / 'login' / USER actor."""
        uid = uuid4()
        event = LoginAttemptEvent(
            username="alice",
            method=LoginMethod.PASSWORD,
            user_id=uid,
            error_type=LoginErrorReason.BAD_PASSWORD,
        )
        handler = LoginAttemptHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "login"
        assert result.actor_id == uid
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == "alice"
        # Business errors have no error_type in structured_data, error is in message
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.error_type is None
        assert "bad_password" in result.event_message

    def test_failed_login_business_error_unknown_user(self) -> None:
        """Failed login with no user_id → SYSTEM actor and actor_id is None."""
        event = LoginAttemptEvent(
            username="notexist",
            method=LoginMethod.PASSWORD,
            error_type=LoginErrorReason.UNKNOWN_USER,
        )
        handler = LoginAttemptHandler()
        result = handler.handle(event)

        assert result.actor_id is None
        assert result.actor_type == PrincipalType.SYSTEM
        assert result.actor_username == "notexist"
        assert result.event_status == EventStatus.ERROR
        assert "unknown_user" in result.event_message

    def test_failed_login_technical_error(self) -> None:
        """Technical error (str error_type) → SECURITY_EVENT / ERROR / ERROR."""
        uid = uuid4()
        event = LoginAttemptEvent(
            username="alice",
            method=LoginMethod.PASSWORD,
            user_id=uid,
            error_type="RedisConnectionError",
        )
        handler = LoginAttemptHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "login"
        assert result.actor_id == uid
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == "alice"
        # Technical errors have error_type in structured_data
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.error_type == "RedisConnectionError"
        assert result.structured_data.error_message == "Look at the Operational Logs for full diagnosis"

    def test_oidc_login_succeeds(self) -> None:
        """Successful OIDC login produces SUCCESS event."""
        uid = uuid4()
        event = LoginAttemptEvent(
            username="carol",
            method=LoginMethod.OIDC,
            user_id=uid,
        )
        handler = LoginAttemptHandler()
        result = handler.handle(event)

        assert result.event_status == EventStatus.SUCCESS
        assert result.actor_id == uid
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == "carol"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "login-context"
        assert result.structured_data.method == LoginMethod.OIDC
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None
        assert result.resource_urn == "urn:syntara:user:carol"
        assert result.resource_name == "carol"

    def test_sa_login_failure_without_user_id_uses_service_account_type(self) -> None:
        """Failed SA login with no user_id but principal_type=SERVICE_ACCOUNT → SERVICE_ACCOUNT actor."""
        event = LoginAttemptEvent(
            username="nx_sa_unknown",
            method=LoginMethod.CLIENT_CREDENTIALS,
            error_type=LoginErrorReason.UNKNOWN_USER,
            principal_type=PrincipalType.SERVICE_ACCOUNT,
        )
        handler = LoginAttemptHandler()
        result = handler.handle(event)

        assert result.actor_id is None
        assert result.actor_type == PrincipalType.SERVICE_ACCOUNT
        assert result.event_status == EventStatus.ERROR

    def test_sa_login_failure_with_user_id_uses_service_account_type(self) -> None:
        """Failed SA login with both user_id and principal_type=SERVICE_ACCOUNT."""
        sa_id = uuid4()
        event = LoginAttemptEvent(
            username="nx_sa_test",
            method=LoginMethod.CLIENT_CREDENTIALS,
            error_type=LoginErrorReason.DISABLED_SERVICE_ACCOUNT,
            user_id=sa_id,
            principal_type=PrincipalType.SERVICE_ACCOUNT,
        )
        handler = LoginAttemptHandler()
        result = handler.handle(event)

        assert result.actor_id == sa_id
        assert result.actor_type == PrincipalType.SERVICE_ACCOUNT

    def test_login_with_no_username(self) -> None:
        """Login attempt with no username → resource_urn and resource_name are None."""
        event = LoginAttemptEvent(
            username=None,
            method=LoginMethod.PASSWORD,
            error_type=LoginErrorReason.UNKNOWN_USER,
        )
        handler = LoginAttemptHandler()
        result = handler.handle(event)

        assert result.actor_username is None
        assert result.resource_urn is None
        assert result.resource_name is None
