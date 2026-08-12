"""Unit tests for AuditContextEvent and AuditContextHandler."""

from syntara.audit.emitter import AuditActorContext

# mypy: disable-error-code="attr-defined"
from syntara.audit.events.audit_context import AuditContextEvent, AuditContextHandler
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType
from syntara.core.models.user import User


class TestAuditContextHandler:
    """Tests for AuditContextHandler audit event handler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """AuditContextHandler is a subclass of AuditEventHandler."""
        handler = AuditContextHandler()
        assert isinstance(handler, AuditEventHandler)

    async def test_successful_operation(self, test_user: User) -> None:
        """Successful operation produces SUCCESS status with original severity."""
        event = AuditContextEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="test_action",
            source_component="test.component",
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
            event_severity=EventSeverity.INFO,
            resource_urn="urn:syntara:test:resource:12345",
            resource_name="test-resource",
            error_type=None,
            error_message=None,
            context_data={"test_field": "test_value"},
        )

        handler = AuditContextHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "test_action"
        assert result.event_message == "Operation test_action completed successfully"
        assert result.source_component == "test.component"
        assert result.resource_urn == "urn:syntara:test:resource:12345"
        assert result.resource_name == "test-resource"
        assert result.actor_id == test_user.id
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == test_user.username

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "context"
        assert result.structured_data.test_field == "test_value"

    def test_error_operation(self) -> None:
        """Error operation produces ERROR status with error details."""
        event = AuditContextEvent(
            event_category=EventCategory.API_EXECUTION,
            event_action="test_action",
            source_component="test.component",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.ERROR,
            resource_urn="urn:syntara:api:endpoint:test_endpoint",
            resource_name="test-endpoint",
            error_type="ValueError",
            error_message="Look at the Operational Logs for full diagnosis",
            context_data={"test_field": "test_value"},
        )

        handler = AuditContextHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.API_EXECUTION
        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "test_action_error"
        assert result.event_message == "Operation test_action failed with ValueError"
        assert result.source_component == "test.component"
        assert result.resource_urn == "urn:syntara:api:endpoint:test_endpoint"
        assert result.resource_name == "test-endpoint"
        assert result.actor_id is None
        assert result.actor_type is None
        assert result.actor_username is None

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "context"
        assert result.structured_data.error_type == "ValueError"
        assert result.structured_data.error_message == "Look at the Operational Logs for full diagnosis"
        assert result.structured_data.test_field == "test_value"

    def test_warning_severity_preserved_on_success(self) -> None:
        """Warning severity is preserved for successful operations."""
        event = AuditContextEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_action="suspicious_activity_detected",
            source_component="security.monitor",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.WARNING,
            error_type=None,
            error_message=None,
            context_data={"ip_address": "192.168.1.1"},
        )

        handler = AuditContextHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.SUCCESS

    def test_critical_severity_preserved_on_error(self) -> None:
        """Critical severity is preserved for error operations."""
        event = AuditContextEvent(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_action="database_backup",
            source_component="backup.service",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.CRITICAL,
            error_type="DatabaseConnectionError",
            error_message="Look at the Operational Logs for full diagnosis",
            context_data={},
        )

        handler = AuditContextHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.CRITICAL
        assert result.event_status == EventStatus.ERROR

    async def test_empty_context_data(self) -> None:
        """Operations with no additional context data work correctly."""
        event = AuditContextEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="logout",
            source_component="auth.service",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.INFO,
            error_type=None,
            error_message=None,
            context_data={},
        )

        handler = AuditContextHandler()
        result = handler.handle(event)

        assert result.event_status == EventStatus.SUCCESS
        assert isinstance(result.structured_data, AuditContextData)
        # Only built-in fields should be present
        structured_dict = result.structured_data.model_dump()
        expected_keys = {"data_type", "error_type", "error_message"}
        assert set(structured_dict.keys()) == expected_keys
        assert result.structured_data.data_type == "context"

    async def test_multiple_context_fields(self) -> None:
        """Multiple context data fields are preserved."""
        event = AuditContextEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="create_workflow",
            source_component="workflows.service",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.INFO,
            error_type=None,
            error_message=None,
            context_data={
                "workflow_name": "test_workflow",
                "workflow_type": "sequential",
                "step_count": 5,
            },
        )

        handler = AuditContextHandler()
        result = handler.handle(event)

        assert result.structured_data.workflow_name == "test_workflow"
        assert result.structured_data.workflow_type == "sequential"
        assert result.structured_data.step_count == 5

    def test_error_without_context_data(self) -> None:
        """Error operations can have no additional context data."""
        event = AuditContextEvent(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_action="health_check",
            source_component="health.service",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.ERROR,
            error_type="ServiceUnavailableError",
            error_message="Look at the Operational Logs for full diagnosis",
            context_data={},
        )

        handler = AuditContextHandler()
        result = handler.handle(event)

        assert result.event_status == EventStatus.ERROR
        assert result.structured_data.error_type == "ServiceUnavailableError"
        assert result.structured_data.error_message == "Look at the Operational Logs for full diagnosis"
