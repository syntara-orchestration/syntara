"""Unit tests for FunctionExecutionEvent and FunctionExecutionHandler."""

from syntara.audit.emitter import AuditActorContext

# mypy: disable-error-code="attr-defined"
from syntara.audit.events.function_execution import FunctionExecutionEvent, FunctionExecutionHandler
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.sanitization import REDACTED
from syntara.core.models.principal import PrincipalType
from syntara.core.models.user import User


class TestFunctionExecutionHandler:
    """Tests for FunctionExecutionHandler audit event handler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """FunctionExecutionHandler is a subclass of AuditEventHandler."""
        handler = FunctionExecutionHandler()
        assert isinstance(handler, AuditEventHandler)

    async def test_successful_execution_user_actor(self, test_user: User) -> None:
        """Successful function execution with USER actor produces SUCCESS status."""
        event = FunctionExecutionEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="create_workflow",
            source_component="workflows.service",
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
            event_severity=EventSeverity.INFO,
            function_args={"name": "test_workflow", "type": "sequential"},
            function_result={"workflow_id": "wf-123", "status": "created"},
            error_type=None,
            error_message=None,
        )

        handler = FunctionExecutionHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "create_workflow"
        assert result.event_message == "Function create_workflow executed successfully"
        assert result.source_component == "workflows.service"
        assert result.actor_id == test_user.id
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == test_user.username

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "function"
        assert result.structured_data.function_args == {"name": "test_workflow", "type": "sequential"}
        assert result.structured_data.function_result == {"workflow_id": "wf-123", "status": "created"}
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    def test_successful_execution_no_actor(self) -> None:
        """Successful function execution with no actor produces SUCCESS status."""
        event = FunctionExecutionEvent(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_action="scheduled_cleanup",
            source_component="maintenance.service",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.INFO,
            function_args={"retention_days": 30},
            function_result={"deleted_count": 42},
            error_type=None,
            error_message=None,
        )

        handler = FunctionExecutionHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SYSTEM_OPERATION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "scheduled_cleanup"
        assert result.event_message == "Function scheduled_cleanup executed successfully"
        assert result.source_component == "maintenance.service"
        assert result.actor_id is None
        assert result.actor_type is None
        assert result.actor_username is None

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "function"
        assert result.structured_data.function_args == {"retention_days": 30}
        assert result.structured_data.function_result == {"deleted_count": 42}

    async def test_error_execution(self, test_user: User) -> None:
        """Error function execution produces ERROR status with error details."""
        event = FunctionExecutionEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="delete_workflow",
            source_component="workflows.service",
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
            event_severity=EventSeverity.INFO,
            function_args={"workflow_id": "wf-456"},
            function_result=None,
            error_type="WorkflowNotFoundError",
            error_message="Look at the Operational Logs for full diagnosis",
        )

        handler = FunctionExecutionHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.ERROR  # Escalated from INFO
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "delete_workflow_error"
        assert result.event_message == "Function delete_workflow failed with WorkflowNotFoundError"
        assert result.source_component == "workflows.service"
        assert result.actor_id == test_user.id
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == test_user.username

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "function"
        assert result.structured_data.error_type == "WorkflowNotFoundError"
        assert result.structured_data.error_message == "Look at the Operational Logs for full diagnosis"
        assert result.structured_data.function_args == {"workflow_id": "wf-456"}
        # function_result should not be in structured_data for errors
        assert not hasattr(result.structured_data, "function_result") or result.structured_data.function_result is None

    def test_error_severity_escalation_from_info(self) -> None:
        """Error execution escalates severity from INFO to ERROR."""
        event = FunctionExecutionEvent(
            event_category=EventCategory.API_EXECUTION,
            event_action="fetch_data",
            source_component="api.client",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.INFO,
            function_args={},
            error_type="ConnectionError",
            error_message="Look at the Operational Logs for full diagnosis",
        )

        handler = FunctionExecutionHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.ERROR

    def test_error_severity_escalation_from_warning(self) -> None:
        """Error execution escalates severity from WARNING to ERROR."""
        event = FunctionExecutionEvent(
            event_category=EventCategory.API_EXECUTION,
            event_action="fetch_data",
            source_component="api.client",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.WARNING,
            function_args={},
            error_type="TimeoutError",
            error_message="Look at the Operational Logs for full diagnosis",
        )

        handler = FunctionExecutionHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.ERROR

    def test_critical_severity_preserved_on_error(self) -> None:
        """Critical severity is preserved for error executions."""
        event = FunctionExecutionEvent(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_action="backup_database",
            source_component="backup.service",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.CRITICAL,
            function_args={},
            error_type="DatabaseConnectionError",
            error_message="Look at the Operational Logs for full diagnosis",
        )

        handler = FunctionExecutionHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.CRITICAL
        assert result.event_status == EventStatus.ERROR

    def test_warning_severity_preserved_on_success(self) -> None:
        """Warning severity is preserved for successful executions."""
        event = FunctionExecutionEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_action="validate_token",
            source_component="auth.service",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.WARNING,
            function_args={"token": REDACTED},
            function_result={"valid": True, "expires_soon": True},
            error_type=None,
            error_message=None,
        )

        handler = FunctionExecutionHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.SUCCESS

    def test_empty_function_args(self) -> None:
        """Function execution with no arguments works correctly."""
        event = FunctionExecutionEvent(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_action="health_check",
            source_component="health.service",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.INFO,
            function_args={},
            function_result={"status": "healthy"},
            error_type=None,
            error_message=None,
        )

        handler = FunctionExecutionHandler()
        result = handler.handle(event)

        assert result.event_status == EventStatus.SUCCESS
        assert result.structured_data.function_args == {}
        assert result.structured_data.function_result == {"status": "healthy"}

    def test_none_function_result_on_success(self) -> None:
        """Function execution with None result (void function) works correctly."""
        event = FunctionExecutionEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="log_event",
            source_component="logging.service",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.INFO,
            function_args={"message": "test"},
            function_result=None,
            error_type=None,
            error_message=None,
        )

        handler = FunctionExecutionHandler()
        result = handler.handle(event)

        assert result.event_status == EventStatus.SUCCESS
        assert result.structured_data.function_args == {"message": "test"}
        # function_result should not be in structured_data when None
        assert not hasattr(result.structured_data, "function_result") or result.structured_data.function_result is None

    async def test_complex_function_args_and_result(self, test_user: User) -> None:
        """Complex nested function args and result are preserved."""
        event = FunctionExecutionEvent(
            event_category=EventCategory.USER_ACTION,
            event_action="execute_workflow",
            source_component="workflows.engine",
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
            event_severity=EventSeverity.INFO,
            function_args={
                "workflow_id": "wf-789",
                "inputs": {"param1": "value1", "param2": [1, 2, 3]},
                "parameters": {"timeout": 300, "retry": True},
            },
            function_result={
                "execution_id": "ex-123",
                "status": "completed",
                "outputs": {"result": "success", "duration": 45.2},
            },
            error_type=None,
            error_message=None,
        )

        handler = FunctionExecutionHandler()
        result = handler.handle(event)

        assert result.structured_data.function_args == {
            "workflow_id": "wf-789",
            "inputs": {"param1": "value1", "param2": [1, 2, 3]},
            "parameters": {"timeout": 300, "retry": True},
        }
        assert result.structured_data.function_result == {
            "execution_id": "ex-123",
            "status": "completed",
            "outputs": {"result": "success", "duration": 45.2},
        }

    def test_function_result_excluded_on_error(self) -> None:
        """Function result is excluded from structured data when error occurs."""
        event = FunctionExecutionEvent(
            event_category=EventCategory.API_EXECUTION,
            event_action="call_external_api",
            source_component="api.client",
            actor_context=AuditActorContext(),
            event_severity=EventSeverity.INFO,
            function_args={"endpoint": "/users"},
            function_result={"data": "should not appear"},  # Result exists but error occurred
            error_type="ValidationError",
            error_message="Look at the Operational Logs for full diagnosis",
        )

        handler = FunctionExecutionHandler()
        result = handler.handle(event)

        assert result.event_status == EventStatus.ERROR
        # When error_type is set, function_result should not be included
        assert not hasattr(result.structured_data, "function_result") or result.structured_data.function_result is None
        assert result.structured_data.error_type == "ValidationError"
