"""Unit tests for audit event emission utilities."""

from contextvars import copy_context
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from syntara.audit.emitter import (
    AuditActorContext,
    activity_id_context_var,
    actor_context_var,
    emit_audit_event,
    execution_id_context_var,
    request_id_context_var,
    workflow_id_context_var,
)
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.sanitization import REDACTED, EventSanitizer, sanitizer
from syntara.core.models.principal import PrincipalType
from syntara.core.models.user import User


class TestEventCaptureSanitizerConfiguration:
    """Test EventCapture sanitizer configuration."""

    def test_default_sanitizer_exists(self) -> None:
        """Test that sanitizer is properly configured at bootstrap."""
        assert sanitizer is not None
        assert isinstance(sanitizer, EventSanitizer)
        assert len(sanitizer.detectors) > 0


class TestEventCaptureEmitAuditEvent:
    """Test EventCapture.emit_audit_event method."""

    @patch("syntara.audit.emitter._do_emit_audit_event")
    def test_emit_audit_event_basic(self, mock_do_emit: Mock) -> None:
        """Test basic audit event emission."""
        # Create test event
        event = AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="test_action",
            actor_id=uuid4(),
            actor_type=PrincipalType.USER,
            source_component="test_component",
            event_message="Test message",
            event_status=EventStatus.SUCCESS,
            structured_data=AuditContextData(data_type="test"),
        )

        # Emit the event
        emit_audit_event(event)

        # Verify _do_emit_audit_event was called once
        mock_do_emit.assert_called_once()

        # Verify the event object passed to _do_emit_audit_event
        call_args = mock_do_emit.call_args[0][0]  # First positional argument
        assert call_args.event_id is not None
        assert call_args.event_category == EventCategory.USER_ACTION
        assert call_args.event_action == "test_action"
        assert call_args.event_status == EventStatus.SUCCESS
        assert call_args.actor_type == PrincipalType.USER
        assert call_args.source_component == "test_component"
        assert call_args.event_message == "Test message"
        assert call_args.structured_data is not None

    @patch("syntara.audit.emitter._do_emit_audit_event")
    def test_emit_audit_event_with_context_injection(self, mock_do_emit: Mock, test_user: User) -> None:
        """Test audit event emission with context injection."""
        test_workflow_id = uuid4()
        test_activity_id = "activity_id"
        test_execution_id = uuid4()

        # Use context copy to isolate the test
        ctx = copy_context()

        def test_in_context() -> None:
            # Set context variables
            actor_context_var.set(
                AuditActorContext(
                    actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
                )
            )
            workflow_id_context_var.set(test_workflow_id)
            activity_id_context_var.set(test_activity_id)
            execution_id_context_var.set(test_execution_id)

            # Create event without actor/context info
            event = AuditEvent(
                event_category=EventCategory.SYSTEM_OPERATION,
                event_action="auto_action",
                actor_type=PrincipalType.SYSTEM,  # Required field, will not be overridden since it's truthy
                source_component="test_component",
                event_message="Auto message",
                structured_data=AuditContextData(data_type="test"),
            )

            # Emit the event
            emit_audit_event(event)

            # Verify _do_emit_audit_event was called
            mock_do_emit.assert_called_once()
            event_obj = mock_do_emit.call_args[0][0]

            # Verify context injection worked for None fields only
            assert event_obj.actor_id == test_user.id
            assert event_obj.actor_username == test_user.username
            assert event_obj.actor_type == PrincipalType.SYSTEM  # Not overridden because it was already set
            assert event_obj.workflow_id == test_workflow_id
            assert event_obj.activity_id == test_activity_id
            assert event_obj.execution_id == test_execution_id

        ctx.run(test_in_context)

    @patch("syntara.audit.emitter._do_emit_audit_event")
    def test_emit_audit_event_no_context_override(self, mock_do_emit: Mock, test_user: User) -> None:
        """Test that existing event values are not overridden by context."""
        event_workflow_id = uuid4()
        context_workflow_id = uuid4()

        # Use context copy to isolate the test
        ctx = copy_context()

        def test_in_context() -> None:
            # Set context variables
            actor_context_var.set(
                AuditActorContext(
                    actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
                )
            )
            workflow_id_context_var.set(context_workflow_id)

            # Create event with existing values
            event = AuditEvent(
                event_category=EventCategory.USER_ACTION,
                event_action="user_action",
                actor_id=test_user.id,  # Should not be overridden
                actor_username=test_user.username,  # Should not be overridden
                actor_type=PrincipalType.USER,
                workflow_id=event_workflow_id,  # Should not be overridden
                source_component="test_component",
                event_message="User message",
                structured_data=AuditContextData(data_type="test"),
            )

            # Emit the event
            emit_audit_event(event)

            # Verify original values were preserved
            event_obj = mock_do_emit.call_args[0][0]
            assert event_obj.actor_id == test_user.id  # Not context_actor_id
            assert event_obj.actor_username == test_user.username  # Not context_actor_id
            assert event_obj.workflow_id == event_workflow_id  # Not context_workflow_id

        ctx.run(test_in_context)

    @patch("syntara.audit.emitter._do_emit_audit_event")
    def test_emit_audit_event_data_sanitization(self, mock_do_emit: Mock) -> None:
        """Test that structured_data is sanitized before emission."""
        # Create event with sensitive data
        event = AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_action="login",
            actor_id=uuid4(),
            actor_type=PrincipalType.USER,
            source_component="auth_service",
            event_message="User login",
            event_status=EventStatus.SUCCESS,
            structured_data=AuditContextData(
                data_type="test",
                username="testuser",
                password="secret123",  # noqa: S106
                email="test@example.com",
                normal_data="safe_value",
            ),
        )

        # Emit the event
        emit_audit_event(event)

        # Verify sanitization occurred
        event_obj = mock_do_emit.call_args[0][0]
        context_data = event_obj.structured_data
        assert isinstance(context_data, AuditContextData)

        assert context_data.username == "testuser"  # type: ignore[attr-defined]
        assert context_data.password == REDACTED  # type: ignore[attr-defined]  # Should be sanitized
        assert context_data.email == "[EMAIL_REDACTED]"  # type: ignore[attr-defined]  # Should be sanitized
        assert context_data.normal_data == "safe_value"  # type: ignore[attr-defined]

    @patch("syntara.audit.emitter._do_emit_audit_event")
    def test_emit_audit_event_comprehensive_sensitive_data_sanitization(self, mock_do_emit: Mock) -> None:
        """Test that all sensitive data patterns are properly sanitized."""
        # Create event with various types of sensitive data
        event = AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_action="authentication",
            actor_id=uuid4(),
            actor_type=PrincipalType.USER,
            source_component="auth_service",
            event_message="User authentication attempt",
            event_status=EventStatus.SUCCESS,
            structured_data=AuditContextData(
                data_type="test",
                # Original patterns
                password="secret123",  # noqa: S106
                secret="mysecret",  # noqa: S106
                token="abc123",  # noqa: S106
                api_key="key123",
                auth="bearer xyz",
                # New comprehensive patterns
                credential="cred123",
                private_key="-----BEGIN PRIVATE KEY-----",
                session="session123",
                cookie="sessionid=abc123",
                jwt="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
                bearer="Bearer token123",
                client_secret="client_secret_abc",  # noqa: S106
                access_token="access_xyz",  # noqa: S106
                refresh_token="refresh_xyz",  # noqa: S106
                # Safe data
                username="testuser",
                normal_data="safe_value",
            ),
        )

        # Emit the event
        emit_audit_event(event)

        # Verify comprehensive sanitization occurred
        event_obj = mock_do_emit.call_args[0][0]
        context_data = event_obj.structured_data
        assert isinstance(context_data, AuditContextData)

        assert context_data.password == REDACTED  # type: ignore[attr-defined]
        assert context_data.secret == REDACTED  # type: ignore[attr-defined]
        assert context_data.token == REDACTED  # type: ignore[attr-defined]
        assert context_data.api_key == REDACTED  # type: ignore[attr-defined]
        assert context_data.auth == REDACTED  # type: ignore[attr-defined]

        assert context_data.credential == REDACTED  # type: ignore[attr-defined]
        assert context_data.private_key == REDACTED  # type: ignore[attr-defined]
        assert context_data.session == REDACTED  # type: ignore[attr-defined]
        assert context_data.cookie == REDACTED  # type: ignore[attr-defined]
        assert context_data.jwt == REDACTED  # type: ignore[attr-defined]
        assert context_data.bearer == REDACTED  # type: ignore[attr-defined]
        assert context_data.client_secret == REDACTED  # type: ignore[attr-defined]
        assert context_data.access_token == REDACTED  # type: ignore[attr-defined]
        assert context_data.refresh_token == REDACTED  # type: ignore[attr-defined]

        # Safe data should remain unchanged
        assert context_data.username == "testuser"  # type: ignore[attr-defined]
        assert context_data.normal_data == "safe_value"  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        ("field_name", "field_value", "expected_result", "test_description"),
        [
            # Safe fields that should NOT be redacted
            ("keyspace", "redis.namespace", "redis.namespace", "legitimate keyspace usage"),
            ("keymap", "user.mappings", "user.mappings", "legitimate keymap usage"),
            ("keyboard", "en-US", "en-US", "legitimate keyboard usage"),
            ("username", "testuser", "testuser", "legitimate username"),
            ("value", "30000", "30000", "legitimate value"),
            ("configuration", "app_config", "app_config", "legitimate configuration"),
            ("endpoint", "/api/v1/users", "/api/v1/users", "legitimate endpoint"),
            # password patterns
            ("password", "secret123", REDACTED, "direct password match"),
            ("user_password", "userpass456", REDACTED, "password with prefix"),
            ("admin_password", "adminpass789", REDACTED, "password with prefix"),
            # secret patterns
            ("secret", "topsecret", REDACTED, "direct secret match"),
            ("client_secret", "oauth_secret_123", REDACTED, "secret with prefix"),
            ("app_secret", "application_secret", REDACTED, "secret with prefix"),
            # token patterns
            ("token", "abc123token", REDACTED, "direct token match"),
            ("auth_token", "bearer_token_456", REDACTED, "token with prefix"),
            ("access_token", "oauth_access_789", REDACTED, "token with prefix"),
            # _key patterns (ends with _key)
            ("key", "database.timeout", REDACTED, "standalone key usage"),
            ("config_key", "app.settings.debug", REDACTED, "_key pattern ending"),
            ("lookup_key", "user.preferences.theme", REDACTED, "_key pattern ending"),
            ("database_key", "db_connection_key", REDACTED, "_key pattern ending"),
            ("api_key", "sk-123abc", REDACTED, "_key pattern ending"),
            ("private_key", "-----BEGIN RSA PRIVATE KEY-----", REDACTED, "_key pattern ending"),
            ("public_key", "-----BEGIN PUBLIC KEY-----", REDACTED, "_key pattern ending"),
            ("encryption_key", "aes256_encryption_key", REDACTED, "_key pattern ending"),
            ("signing_key", "rsa_signing_key", REDACTED, "_key pattern ending"),
            ("access_key", "AKIA1234567890", REDACTED, "_key pattern ending"),
            ("ssh_key", "ssh-rsa AAAAB3NzaC1yc2E...", REDACTED, "_key pattern ending"),
            # key_ patterns (starts with key_)
            ("key_value", "some_key_value", REDACTED, "key_ pattern starting"),
            ("key_store", "redis_key_store", REDACTED, "key_ pattern starting"),
            ("key_manager", "key_management_service", REDACTED, "key_ pattern starting"),
            # auth patterns
            ("auth", "basic_auth_string", REDACTED, "direct auth match"),
            ("oauth", "oauth_token_data", REDACTED, "direct oauth match"),
            ("authentication", "auth_header_data", REDACTED, "direct authentication match"),
            # credential patterns
            ("credential", "user_credentials", REDACTED, "direct credential match"),
            ("credentials", "login_credentials", REDACTED, "direct credentials match"),
            ("user_credential", "account_credential", REDACTED, "credential with prefix"),
            # session patterns
            ("session", "session_id_12345", REDACTED, "direct session match"),
            ("session_id", "sess_abcdef123456", REDACTED, "session with suffix"),
            ("user_session", "active_session_token", REDACTED, "session with prefix"),
            # cookie patterns
            ("cookie", "sessioncookie=value", REDACTED, "direct cookie match"),
            ("auth_cookie", "authentication_cookie", REDACTED, "cookie with prefix"),
            ("session_cookie", "session_cookie_data", REDACTED, "cookie with prefix"),
            # jwt patterns
            ("jwt", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...", REDACTED, "direct jwt match"),
            ("jwt_token", "jwt_bearer_token", REDACTED, "jwt with suffix"),
            ("access_jwt", "access_jwt_token", REDACTED, "jwt with prefix"),
            # bearer patterns
            ("bearer", "Bearer token_value", REDACTED, "direct bearer match"),
            ("bearer_token", "Bearer abc123", REDACTED, "bearer with suffix"),
            ("authorization_bearer", "Bearer xyz789", REDACTED, "bearer with prefix"),
            # authorization_code patterns
            ("authorization_code", "auth_code_123456", REDACTED, "direct authorization_code match"),
            ("oauth_authorization_code", "oauth_code_789", REDACTED, "authorization_code with prefix"),
            ("auth_code", "authorization_code_abc", REDACTED, "auth pattern match"),
            # certificate patterns
            ("certificate", "-----BEGIN CERTIFICATE-----", REDACTED, "direct certificate match"),
            ("ssl_certificate", "x509_certificate_data", REDACTED, "certificate with prefix"),
            ("client_certificate", "client_cert_data", REDACTED, "certificate with prefix"),
            # cert patterns
            ("cert", "certificate_content", REDACTED, "direct cert match"),
            ("ssl_cert", "ssl_certificate", REDACTED, "cert with prefix"),
            ("client_cert", "client_certificate_data", REDACTED, "cert with prefix"),
            # pem patterns
            ("pem", "-----BEGIN PRIVATE KEY-----", REDACTED, "direct pem match"),
            ("pem_file", "certificate.pem_content", REDACTED, "pem with suffix"),
            ("ssl_pem", "ssl_certificate_pem", REDACTED, "pem with prefix"),
        ],
    )
    @patch("syntara.audit.emitter._do_emit_audit_event")
    def test_emit_audit_event_field_redaction(
        self,
        mock_do_emit: Mock,
        field_name: str,
        field_value: str,
        expected_result: str,
        test_description: str,
    ) -> None:
        """Test that specific fields are redacted according to defined patterns from emitter.py L#26-44."""
        # Create event with the specific field to test
        structured_data = {"data_type": "test", field_name: field_value}
        event = AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="field_test",
            event_status=EventStatus.SUCCESS,
            actor_id=uuid4(),
            actor_type=PrincipalType.USER,
            source_component="test_service",
            workflow_id=None,
            activity_id=None,
            execution_id=None,
            event_message=f"Testing {test_description}",
            structured_data=AuditContextData(**structured_data),
        )

        # Emit the event
        emit_audit_event(event)

        # Verify the specific field was handled correctly
        event_obj = mock_do_emit.call_args[0][0]
        # After sanitization, structured_data remains as model but in-place sanitized
        assert event_obj.event_status == EventStatus.SUCCESS
        base_data = event_obj.structured_data
        assert isinstance(base_data, AuditContextData)

        assert getattr(base_data, field_name) == expected_result, (
            f"Field '{field_name}' with value '{field_value}' should result in '{expected_result}' "
            f"for {test_description}, but got '{getattr(base_data, field_name)}'"
        )

    @patch("syntara.audit.emitter._do_emit_audit_event")
    def test_emit_audit_event_complex_structured_data(self, mock_do_emit: Mock) -> None:
        """Test audit event emission with complex nested structured data."""
        # Create event with complex structured data
        event = AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="create_user",
            actor_id=uuid4(),
            actor_type=PrincipalType.USER,
            source_component="user_service",
            event_message="User creation request",
            event_status=EventStatus.SUCCESS,
            structured_data=AuditContextData(
                data_type="test",
                user_info={
                    "username": "testuser",
                    "email": "test@example.com",
                    "preferences": {"theme": "dark", "api_token": "secret_token_123"},
                },
                request_data={
                    "method": "POST",
                    "url": "/api/v1/users",
                    "headers": {"Authorization": "Bearer token123"},
                },
                response_data={"status_code": 201, "message": "User created successfully"},
            ),
        )

        # Emit the event
        emit_audit_event(event)

        # Verify complex data was sanitized appropriately
        event_obj = mock_do_emit.call_args[0][0]
        context_data = event_obj.structured_data
        assert isinstance(context_data, AuditContextData)

        # Check that nested sensitive data was sanitized
        user_info = context_data.user_info  # type: ignore[attr-defined]
        assert user_info["username"] == "testuser"
        assert user_info["email"] == "[EMAIL_REDACTED]"
        assert user_info["preferences"]["theme"] == "dark"
        assert user_info["preferences"]["api_token"] == REDACTED
        request_data = context_data.request_data  # type: ignore[attr-defined]
        assert request_data["method"] == "POST"
        response_data = context_data.response_data  # type: ignore[attr-defined]
        assert response_data["status_code"] == 201

    @patch("syntara.audit.emitter._do_emit_audit_event")
    def test_emit_audit_event_with_request_id_injection(self, mock_do_emit: Mock) -> None:
        """Test that request_id from context is injected into structured_data."""
        test_request_id = uuid4()

        # Use context copy to isolate the test
        ctx = copy_context()

        def test_in_context() -> None:
            # Set request_id context variable
            request_id_context_var.set(test_request_id)

            # Create event without request_id in structured_data
            event = AuditEvent(
                event_category=EventCategory.API_EXECUTION,
                event_action="api_call",
                actor_id=uuid4(),
                actor_type=PrincipalType.USER,
                source_component="api_service",
                event_message="API call executed",
                event_status=EventStatus.SUCCESS,
                structured_data=AuditContextData(data_type="test", endpoint="/api/v1/users"),
            )

            # Emit the event
            emit_audit_event(event)

            # Verify request_id was injected into structured_data
            event_obj = mock_do_emit.call_args[0][0]
            context_data = event_obj.structured_data
            assert isinstance(context_data, AuditContextData)
            assert hasattr(context_data, "request_id")
            assert context_data.request_id == str(test_request_id)

        ctx.run(test_in_context)

    @patch("syntara.audit.emitter._do_emit_audit_event")
    def test_emit_audit_event_no_request_id_override(self, mock_do_emit: Mock) -> None:
        """Test that existing request_id in structured_data is not overridden."""
        existing_request_id = uuid4()
        context_request_id = uuid4()

        # Use context copy to isolate the test
        ctx = copy_context()

        def test_in_context() -> None:
            # Set request_id context variable
            request_id_context_var.set(context_request_id)

            # Create event with existing request_id in structured_data
            event = AuditEvent(
                event_category=EventCategory.API_EXECUTION,
                event_action="api_call",
                actor_id=uuid4(),
                actor_type=PrincipalType.USER,
                source_component="api_service",
                event_message="API call executed",
                event_status=EventStatus.SUCCESS,
                structured_data=AuditContextData(
                    data_type="test",
                    endpoint="/api/v1/users",
                    request_id=str(existing_request_id),
                ),
            )

            # Emit the event
            emit_audit_event(event)

            # Verify original request_id was preserved
            event_obj = mock_do_emit.call_args[0][0]
            context_data = event_obj.structured_data
            assert isinstance(context_data, AuditContextData)
            assert context_data.request_id == str(existing_request_id)  # type: ignore[attr-defined]
            assert context_data.request_id != str(context_request_id)  # type: ignore[attr-defined]

        ctx.run(test_in_context)

    @patch("syntara.audit.emitter._do_emit_audit_event")
    def test_emit_audit_event_without_request_id_context(self, mock_do_emit: Mock) -> None:
        """Test that no request_id is added when context variable is not set."""
        # Create event without setting request_id context variable
        event = AuditEvent(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_action="system_action",
            actor_type=PrincipalType.SYSTEM,
            source_component="system_service",
            event_message="System operation",
            event_status=EventStatus.SUCCESS,
            structured_data=AuditContextData(data_type="test", operation="cleanup"),
        )

        # Emit the event
        emit_audit_event(event)

        # Verify no request_id was added to structured_data
        event_obj = mock_do_emit.call_args[0][0]
        context_data = event_obj.structured_data
        assert isinstance(context_data, AuditContextData)
        assert not hasattr(context_data, "request_id")


class TestEventCaptureIntegration:
    """Integration tests for EventCapture functionality."""

    @patch("syntara.audit.emitter._do_emit_audit_event")
    def test_full_emission_flow(self, mock_do_emit: Mock, test_user: User) -> None:
        """Test the complete flow from event creation to emission."""
        test_workflow_id = uuid4()

        # Use context copy to isolate the test
        ctx = copy_context()

        def test_in_context() -> None:
            # Set up context
            actor_context_var.set(
                AuditActorContext(
                    actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
                )
            )
            workflow_id_context_var.set(test_workflow_id)
            activity_id_context_var.set("activity_id")

            # Create and emit event
            event = AuditEvent(
                event_category=EventCategory.AGENT_INTERACTION,
                event_action="agent_query",
                actor_id=None,  # Will be injected
                actor_username=None,  # Will be injected
                actor_type=PrincipalType.SYSTEM,  # Required field, will NOT be overridden since it's truthy
                source_component="agent_service",
                event_message="User queried agent",
                event_status=EventStatus.SUCCESS,
                structured_data=AuditContextData(
                    data_type="test",
                    query="What is the weather?",
                    password="secret123",  # noqa: S106  # Should be sanitized
                    user_email="user@example.com",  # Should be sanitized
                ),
            )

            emit_audit_event(event)

            # Comprehensive verification
            mock_do_emit.assert_called_once()
            event_obj = mock_do_emit.call_args[0][0]

            # Verify context injection
            assert event_obj.actor_id == test_user.id
            assert event_obj.actor_username == test_user.username
            assert event_obj.actor_type == PrincipalType.SYSTEM  # Not overridden because it was already set
            assert event_obj.workflow_id == test_workflow_id

            # Verify event data
            assert event_obj.event_category == EventCategory.AGENT_INTERACTION
            assert event_obj.event_action == "agent_query"
            assert event_obj.source_component == "agent_service"
            assert event_obj.event_message == "User queried agent"

            # Verify sanitization
            context_data = event_obj.structured_data
            assert isinstance(context_data, AuditContextData)
            assert context_data.query == "What is the weather?"  # type: ignore[attr-defined]
            assert context_data.password == REDACTED  # type: ignore[attr-defined]
            assert context_data.user_email == "[EMAIL_REDACTED]"  # type: ignore[attr-defined]

            # Verify event_id was generated
            assert event_obj.event_id is not None

        ctx.run(test_in_context)

    @patch("syntara.audit.emitter._do_emit_audit_event")
    def test_multiple_events_emission(self, mock_do_emit: Mock) -> None:
        """Test emitting multiple events in sequence."""
        # Create and emit multiple events
        events = [
            AuditEvent(
                event_category=EventCategory.USER_ACTION,
                event_action=f"action_{i}",
                actor_id=uuid4(),
                actor_type=PrincipalType.USER,
                source_component="test_component",
                event_message=f"Test message {i}",
                event_status=EventStatus.SUCCESS,
                structured_data=AuditContextData(data_type="test", index=i),
            )
            for i in range(3)
        ]

        for event in events:
            emit_audit_event(event)

        # Verify all events were emitted
        assert mock_do_emit.call_count == 3

        # Verify each event was logged with correct action
        for i, call in enumerate(mock_do_emit.call_args_list):
            event_obj = call[0][0]  # First positional argument
            assert event_obj.event_action == f"action_{i}"
            context_data = event_obj.structured_data
            assert isinstance(context_data, AuditContextData)
            assert context_data.index == i  # type: ignore[attr-defined]
