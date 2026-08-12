"""Unit tests for ContextPlanningEvent, CancellationEvent and their handlers."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.agent_orchestrator.audit.context_planning import (
    CancellationEvent,
    CancellationHandler,
    ContextPlanningEvent,
    ContextPlanningHandler,
    ContextPlanningPhase,
    ContextPlanningStatus,
)
from syntara.audit.emitter import AuditActorContext
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType
from syntara.core.models.user import User


class TestContextPlanningHandler:
    """Tests for ContextPlanningHandler audit event handler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """ContextPlanningHandler is a subclass of AuditEventHandler."""
        handler = ContextPlanningHandler()
        assert isinstance(handler, AuditEventHandler)

    async def test_started_status_with_user_actor(self, test_user: User) -> None:
        """Started context planning with USER actor produces INFO severity."""
        invocation_id = uuid4()
        execution_id = uuid4()
        request_id = uuid4()
        event = ContextPlanningEvent(
            phase=ContextPlanningPhase.RETRIEVAL,
            status=ContextPlanningStatus.STARTED,
            session_id="session-123",
            invocation_id=invocation_id,
            execution_id=execution_id,
            request_id=request_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
        )

        handler = ContextPlanningHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.AGENT_INTERACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "context_planning"
        assert result.event_message == "Context planning retrieval phase started"
        assert result.source_component == "syntara.agent_orchestrator.context_manager"
        assert result.actor_id == test_user.id
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == test_user.username
        assert result.execution_id == execution_id
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "context_planning"
        assert result.structured_data.phase == "retrieval"
        assert result.structured_data.status == "started"
        assert result.structured_data.session_id == "session-123"
        assert result.structured_data.invocation_id == invocation_id
        assert result.structured_data.request_id == request_id
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    async def test_completed_status_with_document_count(self, test_user: User) -> None:
        """Completed context planning includes document count."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextPlanningEvent(
            phase=ContextPlanningPhase.ASSEMBLY,
            status=ContextPlanningStatus.COMPLETED,
            session_id="session-456",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
            document_count=15,
        )

        handler = ContextPlanningHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_message == "Context planning assembly phase completed"
        assert result.structured_data.phase == "assembly"
        assert result.structured_data.status == "completed"
        assert result.structured_data.document_count == 15

    async def test_failed_status_with_error(self, test_user: User) -> None:
        """Failed context planning produces ERROR severity with error details."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextPlanningEvent(
            phase=ContextPlanningPhase.COMPRESSION,
            status=ContextPlanningStatus.FAILED,
            session_id="session-789",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
            error_type="TokenLimitExceeded",
        )

        handler = ContextPlanningHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.AGENT_INTERACTION
        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "context_planning"
        assert result.event_message == "Context planning compression phase failed"
        assert result.structured_data.error_type == "TokenLimitExceeded"
        assert result.structured_data.error_message == "Look at the Operational Logs for full diagnosis"
        assert result.structured_data.phase == "compression"
        assert result.structured_data.status == "failed"

    def test_cancelled_status(self) -> None:
        """Cancelled context planning produces WARNING severity."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextPlanningEvent(
            phase=ContextPlanningPhase.RETRIEVAL,
            status=ContextPlanningStatus.CANCELLED,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = ContextPlanningHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_message == "Context planning retrieval phase cancelled"
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    def test_all_phases(self) -> None:
        """All context planning phases are supported."""
        invocation_id = uuid4()
        execution_id = uuid4()

        for phase in [
            ContextPlanningPhase.RETRIEVAL,
            ContextPlanningPhase.ASSEMBLY,
            ContextPlanningPhase.COMPRESSION,
        ]:
            event = ContextPlanningEvent(
                phase=phase,
                status=ContextPlanningStatus.STARTED,
                session_id="session-def",
                invocation_id=invocation_id,
                execution_id=execution_id,
                actor_context=AuditActorContext(),
            )

            handler = ContextPlanningHandler()
            result = handler.handle(event)

            assert result.structured_data.phase == phase.value
            assert result.event_message == f"Context planning {phase.value} phase started"

    def test_document_count_optional(self) -> None:
        """Document count is optional."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextPlanningEvent(
            phase=ContextPlanningPhase.ASSEMBLY,
            status=ContextPlanningStatus.COMPLETED,
            session_id="session-ghi",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = ContextPlanningHandler()
        result = handler.handle(event)

        assert result.structured_data.document_count is None

    def test_no_actor_context(self) -> None:
        """Event without actor_context defaults to None actor fields."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextPlanningEvent(
            phase=ContextPlanningPhase.RETRIEVAL,
            status=ContextPlanningStatus.STARTED,
            session_id="session-jkl",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=None,
        )

        handler = ContextPlanningHandler()
        result = handler.handle(event)

        assert result.actor_id is None
        assert result.actor_username is None
        assert result.actor_type is None

    def test_failed_without_error_type(self) -> None:
        """Failed status without explicit error_type still produces error event."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextPlanningEvent(
            phase=ContextPlanningPhase.ASSEMBLY,
            status=ContextPlanningStatus.FAILED,
            session_id="session-mno",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            error_type=None,
        )

        handler = ContextPlanningHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None


class TestCancellationHandler:
    """Tests for CancellationHandler audit event handler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """CancellationHandler is a subclass of AuditEventHandler."""
        handler = CancellationHandler()
        assert isinstance(handler, AuditEventHandler)

    async def test_cancellation_during_retrieval(self, test_user: User) -> None:
        """Cancellation during retrieval phase produces WARNING severity."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = CancellationEvent(
            phase=ContextPlanningPhase.RETRIEVAL,
            session_id="session-pqr",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
        )

        handler = CancellationHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.AGENT_INTERACTION
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "cancellation"
        assert result.event_message == "Invocation cancelled during retrieval phase"
        assert result.source_component == "syntara.agent_orchestrator.context_manager"
        assert result.actor_id == test_user.id
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == test_user.username
        assert result.execution_id == execution_id
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "cancellation"
        assert result.structured_data.phase == "retrieval"
        assert result.structured_data.session_id == "session-pqr"
        assert result.structured_data.invocation_id == invocation_id

    def test_cancellation_during_assembly(self) -> None:
        """Cancellation during assembly phase."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = CancellationEvent(
            phase=ContextPlanningPhase.ASSEMBLY,
            session_id="session-stu",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = CancellationHandler()
        result = handler.handle(event)

        assert result.event_message == "Invocation cancelled during assembly phase"
        assert result.structured_data.phase == "assembly"

    def test_cancellation_during_compression(self) -> None:
        """Cancellation during compression phase."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = CancellationEvent(
            phase=ContextPlanningPhase.COMPRESSION,
            session_id="session-vwx",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = CancellationHandler()
        result = handler.handle(event)

        assert result.event_message == "Invocation cancelled during compression phase"
        assert result.structured_data.phase == "compression"

    def test_no_actor_context(self) -> None:
        """Event without actor_context defaults to None actor fields."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = CancellationEvent(
            phase=ContextPlanningPhase.RETRIEVAL,
            session_id="session-yz",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=None,
        )

        handler = CancellationHandler()
        result = handler.handle(event)

        assert result.actor_id is None
        assert result.actor_username is None
        assert result.actor_type is None

    def test_execution_id_optional(self) -> None:
        """Execution ID is optional."""
        invocation_id = uuid4()
        event = CancellationEvent(
            phase=ContextPlanningPhase.ASSEMBLY,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=None,
            actor_context=AuditActorContext(),
        )

        handler = CancellationHandler()
        result = handler.handle(event)

        assert result.execution_id is None
