"""Unit tests for ContextIntegrationEvent and ContextIntegrationHandler."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.agent_orchestrator.audit.context_integration import (
    ContextIntegrationEvent,
    ContextIntegrationHandler,
    ContextIntegrationStatus,
)
from syntara.audit.emitter import AuditActorContext
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType
from syntara.core.models.user import User


class TestContextIntegrationHandler:
    """Tests for ContextIntegrationHandler audit event handler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """ContextIntegrationHandler is a subclass of AuditEventHandler."""
        handler = ContextIntegrationHandler()
        assert isinstance(handler, AuditEventHandler)

    async def test_success_status_with_user_actor(self, test_user: User) -> None:
        """Successful context integration with USER actor produces SUCCESS status."""
        invocation_id = uuid4()
        execution_id = uuid4()
        request_id = uuid4()
        event = ContextIntegrationEvent(
            status=ContextIntegrationStatus.SUCCESS,
            grounding_score=0.92,
            citations_count=5,
            session_id="session-123",
            invocation_id=invocation_id,
            execution_id=execution_id,
            request_id=request_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
        )

        handler = ContextIntegrationHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.AGENT_INTERACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "context_integration"
        assert result.event_message == "Context integration succeeded"
        assert result.source_component == "syntara.agent_orchestrator.agents.orchestrator"
        assert result.actor_id == test_user.id
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == test_user.username
        assert result.execution_id == execution_id
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "context_integration"
        assert result.structured_data.status == "success"
        assert result.structured_data.session_id == "session-123"
        assert result.structured_data.grounding_score == 0.92
        assert result.structured_data.citations_count == 5
        assert result.structured_data.request_id == request_id
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    async def test_timeout_status_produces_warning(self, test_user: User) -> None:
        """Timeout context integration produces WARNING severity."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextIntegrationEvent(
            status=ContextIntegrationStatus.TIMEOUT,
            session_id="session-789",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
        )

        handler = ContextIntegrationHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_message == "Context integration timed-out"
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    def test_fallback_status_produces_warning(self) -> None:
        """Fallback context integration produces WARNING severity."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextIntegrationEvent(
            status=ContextIntegrationStatus.FALLBACK,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = ContextIntegrationHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_message == "Context integration fell back to original prompt"
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    def test_grounding_score_optional(self) -> None:
        """Grounding score is optional."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextIntegrationEvent(
            status=ContextIntegrationStatus.SUCCESS,
            session_id="session-ghi",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            grounding_score=None,
        )

        handler = ContextIntegrationHandler()
        result = handler.handle(event)

        assert result.structured_data.grounding_score is None

    def test_citations_count_optional(self) -> None:
        """Citations count is optional."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextIntegrationEvent(
            status=ContextIntegrationStatus.SUCCESS,
            session_id="session-jkl",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            citations_count=None,
        )

        handler = ContextIntegrationHandler()
        result = handler.handle(event)

        assert result.structured_data.citations_count is None

    def test_invocation_id_included(self) -> None:
        """Invocation ID is included in structured_data when provided."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextIntegrationEvent(
            status=ContextIntegrationStatus.SUCCESS,
            session_id="session-mno",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = ContextIntegrationHandler()
        result = handler.handle(event)

        assert result.execution_id == execution_id
        assert result.structured_data.invocation_id == invocation_id

    def test_no_actor_context(self) -> None:
        """Event without actor_context handles None gracefully."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextIntegrationEvent(
            status=ContextIntegrationStatus.SUCCESS,
            session_id="session-pqr",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=None,
        )

        handler = ContextIntegrationHandler()
        result = handler.handle(event)

        assert result.actor_id is None
        assert result.actor_username is None
        assert result.actor_type is None

    def test_zero_citations_count(self) -> None:
        """Zero citations count is preserved."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextIntegrationEvent(
            status=ContextIntegrationStatus.SUCCESS,
            session_id="session-stu",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            citations_count=0,
        )

        handler = ContextIntegrationHandler()
        result = handler.handle(event)

        assert result.structured_data.citations_count == 0

    def test_low_grounding_score(self) -> None:
        """Low grounding score is preserved in structured data."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = ContextIntegrationEvent(
            status=ContextIntegrationStatus.SUCCESS,
            session_id="session-vwx",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            grounding_score=0.15,
        )

        handler = ContextIntegrationHandler()
        result = handler.handle(event)

        assert result.structured_data.grounding_score == 0.15
        # Note: low score doesn't change severity - that's a business decision elsewhere
        assert result.event_severity == EventSeverity.INFO
