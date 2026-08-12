"""Unit tests for audit context managers."""

# mypy: disable-error-code="attr-defined"

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from syntara.audit.context_managers import actor_context, audit_context, build_actor_context
from syntara.audit.decorators import audit
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.emitter import (
    activity_id_context_var,
    actor_context_var,
    execution_id_context_var,
    request_id_context_var,
    workflow_id_context_var,
)
from syntara.audit.events.audit_context import AuditContextEvent, AuditContextHandler
from syntara.audit.events.function_execution import FunctionExecutionEvent, FunctionExecutionHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.sanitization import REDACTED
from syntara.core.models.principal import PrincipalType, service_principal_id
from syntara.core.models.user import User


class TestActorContext:
    """Test the actor_context context manager."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register(
            {AuditContextEvent: AuditContextHandler(), FunctionExecutionEvent: FunctionExecutionHandler()}
        )

    async def test_actor_context_sets_and_resets_context_variables(self, test_user: User) -> None:
        """Test that actor_context properly sets and resets context variables."""
        # Arrange
        test_workflow_id = uuid4()
        test_activity_id = "test_activity"
        test_execution_id = uuid4()

        # Act & Assert - context variables should be set inside context
        with actor_context(
            actor=test_user,
            workflow_id=test_workflow_id,
            activity_id=test_activity_id,
            execution_id=test_execution_id,
        ):
            _actor_context = actor_context_var.get()
            assert _actor_context is not None
            assert _actor_context.actor_id == test_user.id
            assert _actor_context.actor_username == test_user.username
            assert _actor_context.actor_type == PrincipalType.USER
            assert workflow_id_context_var.get() == test_workflow_id
            assert activity_id_context_var.get() == test_activity_id
            assert execution_id_context_var.get() == test_execution_id

        # Assert - context variables should be reset after context
        assert actor_context_var.get() is None
        assert workflow_id_context_var.get() is None
        assert activity_id_context_var.get() is None
        assert execution_id_context_var.get() is None

    async def test_actor_context_sets_and_resets_request_id(self) -> None:
        """Test that actor_context sets and resets request_id context variable."""
        test_request_id = uuid4()

        with actor_context(request_id=test_request_id):
            assert request_id_context_var.get() == test_request_id

        assert request_id_context_var.get() is None

    async def test_actor_context_system_actor_with_all_context(self) -> None:
        """Test actor_context with no user (None) and full context IDs.

        This mirrors the Temporal worker use case where workflow metadata
        provides execution context but there is no human actor.
        """
        test_workflow_id = uuid4()
        test_execution_id = uuid4()
        test_request_id = uuid4()
        test_activity_id = "run_script"

        with actor_context(
            workflow_id=test_workflow_id,
            execution_id=test_execution_id,
            request_id=test_request_id,
            activity_id=test_activity_id,
        ):
            _actor_context = actor_context_var.get()
            assert _actor_context is not None
            assert _actor_context.actor_id is None
            assert _actor_context.actor_username is None
            assert _actor_context.actor_type is None
            assert workflow_id_context_var.get() == test_workflow_id
            assert execution_id_context_var.get() == test_execution_id
            assert request_id_context_var.get() == test_request_id
            assert activity_id_context_var.get() == test_activity_id

        assert actor_context_var.get() is None
        assert workflow_id_context_var.get() is None
        assert execution_id_context_var.get() is None
        assert request_id_context_var.get() is None
        assert activity_id_context_var.get() is None

    async def test_actor_context_with_defaults(self) -> None:
        """Test actor_context with default values (actor=None means None)."""
        with actor_context():
            ctx = actor_context_var.get()
            assert ctx is not None
            assert ctx.actor_id is None
            assert ctx.actor_username is None
            assert ctx.actor_type is None
            assert workflow_id_context_var.get() is None
            assert activity_id_context_var.get() is None
            assert execution_id_context_var.get() is None

    async def test_actor_context_resets_on_exception(self, test_user: User) -> None:
        """Test that actor_context resets context variables even when exception occurs."""
        # Arrange
        original_actor_context = actor_context_var.get()
        error_msg = "test error"

        # Act & Assert
        with (
            pytest.raises(ValueError, match="test error"),
            actor_context(actor=test_user),
        ):
            _actor_context = actor_context_var.get()
            assert _actor_context is not None
            assert _actor_context.actor_id == test_user.id
            assert _actor_context.actor_username == test_user.username
            assert _actor_context.actor_type == PrincipalType.USER
            raise ValueError(error_msg)

        # Assert - context should be reset even after exception
        assert actor_context_var.get() == original_actor_context

    async def test_actor_context_resets_request_id_on_exception(self) -> None:
        """Test that request_id is reset even when an exception occurs."""
        test_request_id = uuid4()
        error_msg = "boom"

        with (
            pytest.raises(RuntimeError, match="boom"),
            actor_context(request_id=test_request_id),
        ):
            assert request_id_context_var.get() == test_request_id
            raise RuntimeError(error_msg)

        assert request_id_context_var.get() is None

    async def test_actor_context_nested_contexts(
        self, test_user: User, user_factory: Callable[..., Awaitable["User"]]
    ) -> None:
        """Test nested actor_context managers."""
        # Arrange - create another user for inner context
        inner_user = await user_factory(username="inner_user", email="inner@example.com")

        # Act & Assert
        with actor_context(actor=test_user):
            _actor_context = actor_context_var.get()
            assert _actor_context is not None
            assert _actor_context.actor_id == test_user.id
            assert _actor_context.actor_username == test_user.username
            assert _actor_context.actor_type == PrincipalType.USER

            with actor_context(actor=inner_user):
                _actor_context_inner = actor_context_var.get()
                assert _actor_context_inner is not None
                assert _actor_context_inner.actor_id == inner_user.id
                assert _actor_context_inner.actor_username == inner_user.username
                assert _actor_context_inner.actor_type == PrincipalType.USER

            # Should restore outer context
            _actor_context_final = actor_context_var.get()
            assert _actor_context_final is not None
            assert _actor_context_final.actor_id == test_user.id
            assert _actor_context_final.actor_username == test_user.username
            assert _actor_context_final.actor_type == PrincipalType.USER

        # Should restore original context
        assert actor_context_var.get() is None


class TestActorContextServicePrincipalClassification:
    """Test service principal classification in actor_context context manager."""

    async def test_service_principal_classified_as_service_actor(self) -> None:
        """Test that user with a service principal ID is classified as SERVICE in actor_context."""
        svc_id = service_principal_id("backend.ao.svc")
        service_user = User(
            id=svc_id,
            username="service_user",
            email="service@example.com",
            first_name="Service",
            last_name="User",
            password_hash="not-a-real-hash",  # noqa: S106
        )

        with actor_context(actor=service_user):
            _actor_context = actor_context_var.get()
            assert _actor_context is not None
            assert _actor_context.actor_id == svc_id
            assert _actor_context.actor_username == "service_user"
            assert _actor_context.actor_type == PrincipalType.SERVICE

        assert actor_context_var.get() is None

    async def test_regular_user_classified_as_user_actor(self, test_user: User) -> None:
        """Test that user with a non-service principal ID is classified as USER in actor_context."""
        with actor_context(actor=test_user):
            _actor_context = actor_context_var.get()
            assert _actor_context is not None
            assert _actor_context.actor_id == test_user.id
            assert _actor_context.actor_username == test_user.username
            assert _actor_context.actor_type == PrincipalType.USER

        assert actor_context_var.get() is None


class TestBuildActorContextDuckTyping:
    """Test build_actor_context duck-typing branch for non-User principals."""

    def test_service_account_uses_principal_type_and_name(self) -> None:
        """ServiceAccount has __principal_type__ and name but no username."""
        from syntara.service_accounts.models.service_account import ServiceAccount

        sa = ServiceAccount(
            name="my-bot",
            client_id="cid-test",
            hashed_secret="not-real",  # noqa: S106
            project_id=uuid4(),
            created_by=uuid4(),
        )
        ctx = build_actor_context(sa)

        assert ctx.actor_id == sa.id
        assert ctx.actor_type == PrincipalType.SERVICE_ACCOUNT
        assert ctx.actor_username == "my-bot"

    def test_falls_through_to_name_when_username_is_empty(self) -> None:
        """If a principal has username='' the or-chain falls through to name."""
        from syntara.service_accounts.models.service_account import ServiceAccount

        sa = ServiceAccount(
            name="fallback-name",
            client_id="cid-test2",
            hashed_secret="not-real",  # noqa: S106
            project_id=uuid4(),
            created_by=uuid4(),
        )
        sa.__dict__["username"] = ""
        ctx = build_actor_context(sa)

        assert ctx.actor_username == "fallback-name"
        assert ctx.actor_type == PrincipalType.SERVICE_ACCOUNT

    def test_sa_virtual_principal_uses_instance_principal_type(self) -> None:
        """User with __principal_type__ overridden to SERVICE_ACCOUNT reports correct actor_type."""
        sa_user = User(
            id=uuid4(),
            username="my-sa",
            email="my-sa@internal",
            first_name="my-sa",
            is_enabled=True,
        )
        object.__setattr__(sa_user, "__principal_type__", PrincipalType.SERVICE_ACCOUNT)
        ctx = build_actor_context(sa_user)

        assert ctx.actor_id == sa_user.id
        assert ctx.actor_username == "my-sa"
        assert ctx.actor_type == PrincipalType.SERVICE_ACCOUNT

    def test_none_actor_returns_all_none(self) -> None:
        ctx = build_actor_context(None)
        assert ctx.actor_id is None
        assert ctx.actor_username is None
        assert ctx.actor_type is None


class TestAuditContextServicePrincipalClassification:
    """Test service principal classification in audit_context context manager."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({AuditContextEvent: AuditContextHandler()})

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_service_principal_classified_as_service_actor(self, mock_emit: Mock) -> None:
        """Test that user with a service principal ID is classified as SERVICE in audit_context."""
        svc_id = service_principal_id("backend.ao.svc")
        service_user = User(
            id=svc_id,
            username="service_user",
            email="service@example.com",
            first_name="Service",
            last_name="User",
            password_hash="not-a-real-hash",  # noqa: S106
        )

        with audit_context(
            event_category=EventCategory.USER_ACTION,
            event_action="test_action",
            source_component="test.component",
            actor=service_user,
        ):
            pass

        mock_emit.assert_called_once()
        emitted_event = mock_emit.call_args[0][0]

        assert isinstance(emitted_event, AuditEvent)
        assert emitted_event.actor_id == svc_id
        assert emitted_event.actor_username == "service_user"
        assert emitted_event.actor_type == PrincipalType.SERVICE
        assert emitted_event.event_status == EventStatus.SUCCESS

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_regular_user_classified_as_user_actor(self, mock_emit: Mock, test_user: User) -> None:
        """Test that user with a non-service principal ID is classified as USER in audit_context."""
        with audit_context(
            event_category=EventCategory.USER_ACTION,
            event_action="test_action",
            source_component="test.component",
            actor=test_user,
        ):
            pass

        mock_emit.assert_called_once()
        emitted_event = mock_emit.call_args[0][0]

        assert isinstance(emitted_event, AuditEvent)
        assert emitted_event.actor_id == test_user.id
        assert emitted_event.actor_username == test_user.username
        assert emitted_event.actor_type == PrincipalType.USER
        assert emitted_event.event_status == EventStatus.SUCCESS


class TestAuditContext:
    """Test the audit_context context manager."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register(
            {AuditContextEvent: AuditContextHandler(), FunctionExecutionEvent: FunctionExecutionHandler()}
        )

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_audit_context_success_emits_audit_event(self, mock_emit: Mock, test_user: User) -> None:
        """Test that audit_context emits success event when no exception occurs."""
        # Arrange
        test_context_data: dict[str, Any] = {"test_field": "test_value"}

        # Act
        with audit_context(
            event_category=EventCategory.USER_ACTION,
            event_action="test_action",
            source_component="test.component",
            actor=test_user,
            **test_context_data,
        ):
            pass  # Successful execution

        # Assert
        mock_emit.assert_called_once()
        emitted_event = mock_emit.call_args[0][0]

        assert isinstance(emitted_event, AuditEvent)
        assert emitted_event.event_category == EventCategory.USER_ACTION
        assert emitted_event.event_severity == EventSeverity.INFO
        assert emitted_event.event_action == "test_action"
        assert emitted_event.event_message == "Operation test_action completed successfully"
        assert emitted_event.source_component == "test.component"
        assert emitted_event.actor_id == test_user.id
        assert emitted_event.actor_type == PrincipalType.USER
        assert emitted_event.actor_username == test_user.username

        assert emitted_event.event_status == EventStatus.SUCCESS
        assert isinstance(emitted_event.structured_data, AuditContextData)
        # Access additional fields through model_dump since extra="allow"
        structured_dict = emitted_event.structured_data.model_dump()
        assert structured_dict["test_field"] == "test_value"

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_audit_context_with_valid_resource_urn(self, mock_emit: Mock, test_user: User) -> None:
        """Test that audit_context includes valid resource_urn and resource_name in emitted event."""
        # Arrange
        valid_urn = "urn:syntara:test:resource:12345"
        resource_name = "test-resource"

        # Act
        with audit_context(
            event_category=EventCategory.USER_ACTION,
            event_action="test_action",
            source_component="test.component",
            actor=test_user,
            resource_urn=valid_urn,
            resource_name=resource_name,
        ):
            pass  # Successful execution

        # Assert
        mock_emit.assert_called_once()
        emitted_event = mock_emit.call_args[0][0]

        assert isinstance(emitted_event, AuditEvent)
        assert emitted_event.resource_urn == valid_urn
        assert emitted_event.resource_name == resource_name
        assert emitted_event.event_category == EventCategory.USER_ACTION
        assert emitted_event.event_status == EventStatus.SUCCESS

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_audit_context_with_invalid_resource_urn(self, mock_emit: Mock, test_user: User) -> None:
        """Test that audit_context drops invalid resource_urn with warning."""
        import structlog

        from syntara.audit.models import audit_event as audit_event_module

        # Arrange
        invalid_urn = "invalid-urn-format"

        # Replace the module-level logger with a fresh instance.
        # Under xdist, cache_logger_on_first_use=True may have cached a
        # bound logger that bypasses capture_logs()'s processor replacement.
        # A fresh logger created inside capture_logs() context will bind
        # to the capture processor chain.
        old_logger = audit_event_module.logger
        try:
            with structlog.testing.capture_logs() as captured:
                audit_event_module.logger = structlog.get_logger("syntara.audit.models.audit_event")
                with audit_context(
                    event_category=EventCategory.USER_ACTION,
                    event_action="test_action",
                    source_component="test.component",
                    actor=test_user,
                    resource_urn=invalid_urn,
                ):
                    pass  # Successful execution
        finally:
            audit_event_module.logger = old_logger

        # Assert
        mock_emit.assert_called_once()
        emitted_event = mock_emit.call_args[0][0]

        assert isinstance(emitted_event, AuditEvent)
        assert emitted_event.resource_urn is None
        assert emitted_event.event_category == EventCategory.USER_ACTION
        assert emitted_event.event_status == EventStatus.SUCCESS
        # Verify warning was logged
        assert any("does not conform to RFC 8141" in entry.get("event", "") for entry in captured)

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_audit_context_error_emits_error_event(self, mock_emit: Mock) -> None:
        """Test that audit_context emits error event when exception occurs."""
        # Arrange
        test_context_data: dict[str, Any] = {"test_field": "test_value"}
        error_msg = "test error"

        # Act & Assert - Use actor=None (no actor)
        with (
            pytest.raises(ValueError, match="test error"),
            audit_context(
                event_category=EventCategory.API_EXECUTION,
                event_action="test_action",
                source_component="test.component",
                actor=None,
                **test_context_data,
            ),
        ):
            raise ValueError(error_msg)

        # Assert
        mock_emit.assert_called_once()
        emitted_event = mock_emit.call_args[0][0]

        assert isinstance(emitted_event, AuditEvent)
        assert emitted_event.event_category == EventCategory.API_EXECUTION
        # Default severity (INFO) is escalated to ERROR on exception
        assert emitted_event.event_severity == EventSeverity.ERROR
        assert emitted_event.event_action == "test_action_error"
        assert emitted_event.event_message == "Operation test_action failed with ValueError"
        assert emitted_event.source_component == "test.component"
        assert emitted_event.actor_type is None
        assert emitted_event.actor_username is None

        assert emitted_event.event_status == EventStatus.ERROR
        assert isinstance(emitted_event.structured_data, AuditContextData)
        assert emitted_event.structured_data.error_type == "ValueError"
        assert emitted_event.structured_data.error_message == "Look at the Operational Logs for full diagnosis"
        # Access additional fields through model_dump since extra="allow"
        structured_dict = emitted_event.structured_data.model_dump()
        assert structured_dict["test_field"] == "test_value"

    @pytest.mark.parametrize(
        ("exception", "sensitive_pattern"),
        [
            (ValueError("Invalid password: secret123"), "secret123"),
            (RuntimeError("Token abc123xyz expired"), "abc123xyz"),
            (KeyError("Missing API key: sk-1234567890abcdef"), "sk-1234567890abcdef"),
            (Exception("Authentication failed with credentials: user:pass"), "user:pass"),
        ],
        ids=["password", "token", "api_key", "credentials"],
    )
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_audit_context_sanitizes_sensitive_data_in_exception_messages(
        self, mock_emit: Mock, exception: Exception, sensitive_pattern: str
    ) -> None:
        """Test that exception messages with sensitive data are sanitized and don't leak into audit events."""
        # Raise the exception within audit context
        with (
            pytest.raises(type(exception)),
            audit_context(
                event_category=EventCategory.SECURITY_EVENT,
                event_action="test_action",
                source_component="test.component",
                actor=None,
            ),
        ):
            raise exception

        # Should have emitted one event
        mock_emit.assert_called_once()
        emitted_event = mock_emit.call_args[0][0]
        exception_message = str(exception)

        # 1. error_message should be the generic sanitized message
        assert emitted_event.structured_data.error_message == "Look at the Operational Logs for full diagnosis"

        # 2. error_type should be captured correctly
        assert emitted_event.structured_data.error_type == type(exception).__name__

        # 3. event_message should NOT contain the raw exception text with sensitive data
        assert exception_message not in emitted_event.event_message
        # event_message should be generic like "Operation test_action failed with ValueError"
        assert "test_action" in emitted_event.event_message
        assert type(exception).__name__ in emitted_event.event_message

        # 4. Verify sensitive pattern is NOT in any audit event field
        event_dict = emitted_event.model_dump()
        for field_name, field_value in event_dict.items():
            if isinstance(field_value, str):
                assert sensitive_pattern not in field_value, (
                    f"Sensitive data '{sensitive_pattern}' leaked into field '{field_name}'"
                )

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_audit_context_with_no_context_data(self, mock_emit: Mock) -> None:
        """Test audit_context with no additional context data."""
        # Act
        with audit_context(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_action="simple_action",
            source_component="simple.component",
            actor=None,
        ):
            pass

        # Assert
        mock_emit.assert_called_once()
        emitted_event = mock_emit.call_args[0][0]

        assert emitted_event.event_status == EventStatus.SUCCESS
        assert isinstance(emitted_event.structured_data, AuditContextData)
        assert emitted_event.actor_type is None
        assert emitted_event.actor_username is None
        # Should only have base fields (data_type, error_type, error_message with defaults)
        structured_dict = emitted_event.structured_data.model_dump()
        expected_keys = {"data_type", "error_type", "error_message"}
        assert set(structured_dict.keys()) == expected_keys
        assert structured_dict["error_type"] is None
        assert structured_dict["error_message"] is None

    @pytest.mark.parametrize("field_name", ["error_type", "error_message"])
    async def test_audit_context_rejects_reserved_field_names(self, field_name: str, test_user: User) -> None:
        """Test that audit_context raises ValueError when context_data contains reserved fields."""
        with (
            pytest.raises(ValueError, match="Reserved audit field names"),
            audit_context(
                event_category=EventCategory.USER_ACTION,
                event_action="test_action",
                source_component="test.component",
                actor=test_user,
                event_severity=EventSeverity.INFO,
                **{field_name: "injected_value"},
            ),
        ):
            pass  # pragma: no cover

    async def test_audit_context_rejects_multiple_reserved_fields(self, test_user: User) -> None:
        """Test that audit_context rejects multiple reserved fields at once."""
        with (
            pytest.raises(ValueError, match="Reserved audit field names"),
            audit_context(
                event_category=EventCategory.USER_ACTION,
                event_action="test_action",
                source_component="test.component",
                actor=test_user,
                error_type="injected",
                error_message="injected",
            ),
        ):
            pass  # pragma: no cover

    @pytest.mark.parametrize(
        ("severity", "category", "action", "source_component"),
        [
            (EventSeverity.WARNING, EventCategory.SECURITY_EVENT, "security_check", "security.module"),
            (EventSeverity.ERROR, EventCategory.LLM_INTERACTION, "llm_operation", "llm.service"),
            (EventSeverity.CRITICAL, EventCategory.SYSTEM_OPERATION, "critical_operation", "critical.module"),
        ],
    )
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_audit_context_custom_severity_success(
        self,
        mock_emit: Mock,
        severity: EventSeverity,
        category: EventCategory,
        action: str,
        source_component: str,
        test_user: User,
    ) -> None:
        """Test audit_context with custom severity levels for successful operations."""
        # Act
        with audit_context(
            event_category=category,
            event_action=action,
            source_component=source_component,
            event_severity=severity,
            actor=test_user,
        ):
            pass

        # Assert
        mock_emit.assert_called_once()
        emitted_event = mock_emit.call_args[0][0]

        assert emitted_event.event_category == category
        assert emitted_event.event_severity == severity
        assert emitted_event.event_action == action
        assert emitted_event.event_message == f"Operation {action} completed successfully"
        assert emitted_event.source_component == source_component
        assert emitted_event.event_status == EventStatus.SUCCESS

    @pytest.mark.parametrize(
        ("declared_severity", "expected_error_severity", "category", "action", "source_component"),
        [
            # INFO and WARNING escalate to ERROR on exception
            (
                EventSeverity.INFO,
                EventSeverity.ERROR,
                EventCategory.USER_ACTION,
                "info_operation",
                "info.module",
            ),
            (
                EventSeverity.WARNING,
                EventSeverity.ERROR,
                EventCategory.SECURITY_EVENT,
                "security_check",
                "security.module",
            ),
            # ERROR stays ERROR (no-op escalation)
            (
                EventSeverity.ERROR,
                EventSeverity.ERROR,
                EventCategory.LLM_INTERACTION,
                "llm_operation",
                "llm.service",
            ),
            # CRITICAL is preserved — never downgraded to ERROR
            (
                EventSeverity.CRITICAL,
                EventSeverity.CRITICAL,
                EventCategory.SYSTEM_OPERATION,
                "critical_operation",
                "critical.module",
            ),
        ],
    )
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_audit_context_severity_escalated_on_exception(
        self,
        mock_emit: Mock,
        declared_severity: EventSeverity,
        expected_error_severity: EventSeverity,
        category: EventCategory,
        action: str,
        source_component: str,
        test_user: User,
    ) -> None:
        """Custom severity is escalated to at least ERROR on exception; CRITICAL is preserved."""
        # Act & Assert
        with (
            pytest.raises(ValueError, match="test error"),
            audit_context(
                event_category=category,
                event_action=action,
                source_component=source_component,
                event_severity=declared_severity,
                actor=test_user,
            ),
        ):
            error_msg = "test error"
            raise ValueError(error_msg)

        # Assert
        mock_emit.assert_called_once()
        emitted_event = mock_emit.call_args[0][0]

        assert emitted_event.event_category == category
        assert emitted_event.event_severity == expected_error_severity
        assert emitted_event.event_action == f"{action}_error"
        assert emitted_event.event_message == f"Operation {action} failed with ValueError"
        assert emitted_event.source_component == source_component
        assert emitted_event.event_status == EventStatus.ERROR


class TestContextManagersWithTrackEventDecorator:
    """Test context managers working with @audit decorator."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register(
            {AuditContextEvent: AuditContextHandler(), FunctionExecutionEvent: FunctionExecutionHandler()}
        )

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_actor_context_with_audit_decorator(self, mock_emit: Mock, test_user: User) -> None:
        """Test that actor_context provides context for @audit decorated function."""

        # Arrange
        @audit(EventCategory.USER_ACTION, capture_args=True)
        def test_function(param1: str) -> str:
            return f"result_{param1}"

        # Act
        with actor_context(actor=test_user):
            result = test_function("test_value")

        # Assert
        assert result == "result_test_value"
        # Decorator emits 1 event (complete only), actor_context emits 0 events
        assert mock_emit.call_count == 1

        emitted_event = mock_emit.call_args[0][0]
        assert emitted_event.actor_id == test_user.id
        assert emitted_event.actor_type == PrincipalType.USER
        assert emitted_event.actor_username == test_user.username
        assert isinstance(emitted_event.structured_data, AuditContextData)
        assert emitted_event.structured_data.function_args == {"param1": "test_value"}

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_audit_context_with_audit_decorator_success(self, mock_emit: Mock, test_user: User) -> None:
        """Test audit_context with @audit decorated function - success case."""

        # Arrange
        @audit(EventCategory.API_EXECUTION)
        def test_function() -> str:
            return "success"

        # Act
        with audit_context(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_action="wrapper_operation",
            source_component="test.wrapper",
            actor=test_user,
        ):
            result = test_function()

        # Assert
        assert result == "success"

        # Decorator emits 1 event (complete only), context manager emits 1 event
        assert mock_emit.call_count == 2

        # Verify decorator complete event (first call, index 0)
        decorator_event = mock_emit.call_args_list[0][0][0]
        assert decorator_event.event_category == EventCategory.API_EXECUTION
        assert decorator_event.event_action == "test_function"
        assert decorator_event.actor_type == PrincipalType.USER
        assert decorator_event.actor_username == test_user.username

        # Verify context manager event (second call, index 1)
        context_event = mock_emit.call_args_list[1][0][0]
        assert context_event.event_category == EventCategory.SYSTEM_OPERATION
        assert context_event.event_action == "wrapper_operation"
        assert context_event.actor_type == PrincipalType.USER
        assert context_event.event_status == EventStatus.SUCCESS

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_audit_context_with_audit_decorator_error(self, mock_emit: Mock) -> None:
        """Test audit_context with @audit decorated function - error case."""
        # Arrange
        error_msg = "function error"

        @audit(EventCategory.API_EXECUTION)
        def test_function() -> str:
            raise RuntimeError(error_msg)

        # Act & Assert - Use actor=None (no actor)
        with (
            pytest.raises(RuntimeError, match="function error"),
            audit_context(
                event_category=EventCategory.SYSTEM_OPERATION,
                event_action="wrapper_operation",
                source_component="test.wrapper",
                actor=None,
            ),
        ):
            test_function()

        # Assert
        # Decorator emits 1 event (error only), context manager emits 1 error event
        assert mock_emit.call_count == 2

        # Verify decorator error event (first call, index 0)
        decorator_event = mock_emit.call_args_list[0][0][0]
        assert decorator_event.event_category == EventCategory.API_EXECUTION
        assert decorator_event.event_action == "test_function_error"
        assert decorator_event.actor_type is None
        assert decorator_event.actor_username is None

        # Verify context manager error event (second call, index 1)
        context_event = mock_emit.call_args_list[1][0][0]
        assert context_event.event_category == EventCategory.SYSTEM_OPERATION
        assert context_event.event_action == "wrapper_operation_error"
        assert context_event.actor_type is None
        assert context_event.actor_username is None
        assert context_event.event_status == EventStatus.ERROR
        assert context_event.structured_data.error_type == "RuntimeError"

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_nested_context_managers_with_audit(self, mock_emit: Mock) -> None:
        """Test nested actor_context and audit_context with @audit decorator."""
        # Arrange
        test_workflow_id = uuid4()

        @audit(EventCategory.USER_ACTION, capture_result=True)
        def test_function(value: str) -> dict[str, str]:
            return {"result": f"processed_{value}"}

        # Act - Use actor=None (no actor)
        with actor_context(
            actor=None,
            workflow_id=test_workflow_id,
        ):
            result = test_function("test_data")

        # Assert
        assert result == {"result": "processed_test_data"}
        # Decorator emits 1 event (complete only), actor_context emits 0 events
        assert mock_emit.call_count == 1

        emitted_event = mock_emit.call_args[0][0]
        assert emitted_event.actor_id is None
        assert emitted_event.actor_type is None
        assert emitted_event.actor_username is None
        assert emitted_event.workflow_id == test_workflow_id
        assert isinstance(emitted_event.structured_data, AuditContextData)
        assert emitted_event.structured_data.function_result == {"result": "processed_test_data"}

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_async_function_with_actor_context(self, mock_emit: Mock) -> None:
        """Test actor_context with async @audit decorated function."""

        # Arrange
        @audit(EventCategory.API_EXECUTION)
        async def async_test_function(param: str) -> str:
            return f"async_result_{param}"

        # Act - Use actor=None (no actor)
        with actor_context(actor=None):
            result = await async_test_function("test")

        # Assert
        assert result == "async_result_test"
        # Decorator emits 1 event (complete only), actor_context emits 0 events
        assert mock_emit.call_count == 1

        emitted_event = mock_emit.call_args[0][0]
        assert emitted_event.actor_id is None
        assert emitted_event.actor_type is None
        assert emitted_event.actor_username is None
        assert emitted_event.event_action == "async_test_function"


class TestActorContextSanitizationAndTruncation:
    """Test that events emitted within actor_context have sanitized and truncated payloads."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register(
            {AuditContextEvent: AuditContextHandler(), FunctionExecutionEvent: FunctionExecutionHandler()}
        )

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_actor_context_emitted_event_has_sanitized_payload(self, mock_emit: Mock, test_user: User) -> None:
        """Test that sensitive data in captured arguments is redacted when using actor_context."""

        @audit(EventCategory.USER_ACTION, capture_args=True)
        def test_function(api_secret: str, name: str) -> str:
            return "ok"

        with actor_context(actor=test_user):
            test_function("my_secret_key", "alice")

        emitted_event = mock_emit.call_args[0][0]
        assert emitted_event.actor_type == PrincipalType.USER
        assert emitted_event.actor_username == test_user.username
        function_data = emitted_event.structured_data
        assert isinstance(function_data, AuditContextData)

        # Secret field should be redacted by the sanitizer
        assert isinstance(function_data.function_args, dict)
        assert function_data.function_args["api_secret"] == REDACTED
        # Non-sensitive field should be preserved
        assert function_data.function_args["name"] == "alice"

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_actor_context_emitted_event_has_truncated_payload(self, mock_emit: Mock, test_user: User) -> None:
        """Test that oversized captured results are truncated when using actor_context."""

        @audit(EventCategory.USER_ACTION, capture_result=True)
        def test_function() -> dict[str, str]:
            return {"large_value": "x" * 20_000}

        with actor_context(actor=test_user):
            test_function()

        emitted_event = mock_emit.call_args[0][0]
        assert emitted_event.actor_type == PrincipalType.USER
        assert emitted_event.actor_username == test_user.username
        function_data = emitted_event.structured_data
        assert isinstance(function_data, AuditContextData)

        # The dict structure should be preserved with truncated string leaves
        assert isinstance(function_data.function_result, dict)
        assert "...<truncated>" in function_data.function_result["large_value"]


class TestAuditContextSanitizationAndTruncation:
    """Test that events emitted by audit_context have sanitized and truncated payloads."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register(
            {AuditContextEvent: AuditContextHandler(), FunctionExecutionEvent: FunctionExecutionHandler()}
        )

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_audit_context_emitted_event_has_sanitized_payload(self, mock_emit: Mock, test_user: User) -> None:
        """Test that sensitive data in context_data is redacted by audit_context."""
        with audit_context(
            event_category=EventCategory.USER_ACTION,
            event_action="test_action",
            source_component="test.component",
            actor=test_user,
            user_password="super_secret",  # noqa: S106
            username="alice",
        ):
            pass

        emitted_event = mock_emit.call_args[0][0]
        assert emitted_event.actor_type == PrincipalType.USER
        assert emitted_event.actor_username == test_user.username
        assert emitted_event.event_status == EventStatus.SUCCESS
        assert isinstance(emitted_event.structured_data, AuditContextData)

        structured_dict = emitted_event.structured_data.model_dump()
        # Password field should be redacted by the sanitizer
        assert structured_dict["user_password"] == REDACTED
        # Non-sensitive field should be preserved
        assert structured_dict["username"] == "alice"

    @pytest.mark.parametrize(
        ("sensitive_field_name", "sensitive_value"),
        [
            pytest.param("token", "abc123xyz", id="token"),
            pytest.param("api_key", "sk-1234567890abcdef", id="api_key"),
            pytest.param("secret", "my_secret_value", id="secret"),
            pytest.param("credentials", "user:pass", id="credentials"),
        ],
    )
    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_audit_context_sanitizes_credential_patterns_in_context_data(
        self,
        mock_emit: Mock,
        sensitive_field_name: str,
        sensitive_value: str,
        test_user: User,
    ) -> None:
        """Test that common credential patterns in context_data are redacted by audit_context.

        This test verifies that when sensitive credential patterns (token, api_key, secret,
        credentials) are passed as keyword arguments to audit_context(), they are properly
        sanitized to "[REDACTED]" in the emitted audit event's structured_data.

        The sanitization should be selective - only sensitive fields are redacted while
        non-sensitive fields preserve their original values.
        """
        # Build kwargs dynamically with one sensitive field and one non-sensitive field
        context_kwargs: dict[str, Any] = {
            sensitive_field_name: sensitive_value,
            "username": "alice",  # Non-sensitive field for verification
        }

        with audit_context(
            event_category=EventCategory.USER_ACTION,
            event_action="test_action",
            source_component="test.component",
            actor=test_user,
            **context_kwargs,
        ):
            pass

        emitted_event = mock_emit.call_args[0][0]
        assert emitted_event.actor_type == PrincipalType.USER
        assert emitted_event.actor_username == test_user.username
        assert emitted_event.event_status == EventStatus.SUCCESS
        assert isinstance(emitted_event.structured_data, AuditContextData)

        structured_dict = emitted_event.structured_data.model_dump()
        # Sensitive credential field should be redacted by the sanitizer
        assert structured_dict[sensitive_field_name] == REDACTED
        # Non-sensitive field should be preserved
        assert structured_dict["username"] == "alice"
        # Original sensitive value should not appear anywhere in the structured data
        assert sensitive_value not in str(structured_dict)

    @patch("syntara.audit.emitter._do_emit_audit_event")
    async def test_audit_context_emitted_event_has_truncated_payload(self, mock_emit: Mock, test_user: User) -> None:
        """Test that oversized context_data is truncated by audit_context."""
        with audit_context(
            event_category=EventCategory.USER_ACTION,
            event_action="test_action",
            source_component="test.component",
            actor=test_user,
            large_field="x" * 20_000,
        ):
            pass

        emitted_event = mock_emit.call_args[0][0]
        assert emitted_event.actor_type == PrincipalType.USER
        assert emitted_event.actor_username == test_user.username
        assert emitted_event.event_status == EventStatus.SUCCESS
        assert isinstance(emitted_event.structured_data, AuditContextData)

        structured_dict = emitted_event.structured_data.model_dump()
        # The large field should have been truncated
        assert "...<truncated>" in structured_dict["large_field"]
