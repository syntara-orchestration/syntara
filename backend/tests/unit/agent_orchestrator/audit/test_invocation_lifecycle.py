"""Unit tests for InvocationLifecycleEvent and InvocationLifecycleHandler."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.agent_orchestrator.audit.invocation_lifecycle import (
    InvocationLifecycleEvent,
    InvocationLifecycleHandler,
)
from syntara.agent_orchestrator.models import InvocationStatus
from syntara.audit.emitter import AuditActorContext
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType
from syntara.core.models.user import User


class TestInvocationLifecycleHandler:
    """Tests for InvocationLifecycleHandler audit event handler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """InvocationLifecycleHandler is a subclass of AuditEventHandler."""
        handler = InvocationLifecycleHandler()
        assert isinstance(handler, AuditEventHandler)

    async def test_running_status_with_user_actor(self, test_user: User) -> None:
        """Running invocation with USER actor produces SUCCESS status."""
        invocation_id = uuid4()
        execution_id = uuid4()
        request_id = uuid4()
        event = InvocationLifecycleEvent(
            status=InvocationStatus.RUNNING,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            request_id=request_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
        )

        handler = InvocationLifecycleHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.AGENT_INTERACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "invocation_running"
        assert result.event_message == "Invocation running"
        assert result.source_component == "syntara.agent_orchestrator.executor"
        assert result.actor_id == test_user.id
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == test_user.username
        assert result.execution_id == execution_id
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "invocation_lifecycle"
        assert result.structured_data.invocation_status == InvocationStatus.RUNNING
        assert result.structured_data.request_id == request_id
        assert result.structured_data.error_type is None

    async def test_failed_status_with_error(self, test_user: User) -> None:
        """Failed invocation produces ERROR severity with error details."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = InvocationLifecycleEvent(
            status=InvocationStatus.FAILED,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
            error_type="LLMConnectionError",
        )

        handler = InvocationLifecycleHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.AGENT_INTERACTION
        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "invocation_failed"
        assert result.event_message == "Invocation failed"
        assert result.source_component == "syntara.agent_orchestrator.executor"

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.error_type == "LLMConnectionError"
        assert result.structured_data.invocation_status == InvocationStatus.FAILED

    def test_cancelled_status_produces_warning(self) -> None:
        """Cancelled invocation produces WARNING severity."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = InvocationLifecycleEvent(
            status=InvocationStatus.CANCELLED,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = InvocationLifecycleHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "invocation_cancelled"
        assert result.event_message == "Invocation cancelled"
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    def test_metadata_fields_included(self) -> None:
        """Metadata fields (model_name, total_token_count, conversion_failures) are included."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = InvocationLifecycleEvent(
            status=InvocationStatus.COMPLETED,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            model_name="claude-3-5-sonnet",
        )

        handler = InvocationLifecycleHandler()
        result = handler.handle(event)

        assert result.structured_data.model_name == "claude-3-5-sonnet"

    def test_metadata_fields_optional(self) -> None:
        """Metadata fields are optional."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = InvocationLifecycleEvent(
            status=InvocationStatus.RUNNING,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = InvocationLifecycleHandler()
        result = handler.handle(event)

        assert result.structured_data.model_name is None

    def test_invocation_id_included(self) -> None:
        """Invocation ID is included in structured_data when provided."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = InvocationLifecycleEvent(
            status=InvocationStatus.RUNNING,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = InvocationLifecycleHandler()
        result = handler.handle(event)

        assert result.execution_id == execution_id
        assert result.structured_data.invocation_id == invocation_id

    def test_no_actor_context(self) -> None:
        """Event without actor_context handles None gracefully."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = InvocationLifecycleEvent(
            status=InvocationStatus.COMPLETED,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=None,
        )

        handler = InvocationLifecycleHandler()
        result = handler.handle(event)

        assert result.actor_id is None
        assert result.actor_username is None
        assert result.actor_type is None

    def test_status_case_insensitive(self) -> None:
        """Status is converted to lowercase for action and message."""
        invocation_id = uuid4()
        execution_id = uuid4()
        # InvocationStatus values are typically uppercase
        event = InvocationLifecycleEvent(
            status=InvocationStatus.RUNNING,  # This is "RUNNING" as an enum
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = InvocationLifecycleHandler()
        result = handler.handle(event)

        # Should be lowercased
        assert result.event_action == "invocation_running"
        assert result.event_message == "Invocation running"

    def test_failed_without_error_type(self) -> None:
        """Failed status without explicit error_type still produces error event."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = InvocationLifecycleEvent(
            status=InvocationStatus.FAILED,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            error_type=None,
        )

        handler = InvocationLifecycleHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.structured_data.error_type is None
