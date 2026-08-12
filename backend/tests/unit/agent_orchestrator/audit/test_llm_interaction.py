"""Unit tests for LLMInteractionEvent and LLMInteractionHandler."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.agent_orchestrator.audit.llm_interaction import (
    LLMInteractionEvent,
    LLMInteractionHandler,
    LLMInteractionStatus,
    LLMInteractionType,
)
from syntara.audit.emitter import AuditActorContext
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType
from syntara.core.models.user import User


class TestLLMInteractionHandler:
    """Tests for LLMInteractionHandler audit event handler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        """LLMInteractionHandler is a subclass of AuditEventHandler."""
        handler = LLMInteractionHandler()
        assert isinstance(handler, AuditEventHandler)

    async def test_successful_standard_interaction(self, test_user: User) -> None:
        """Successful standard LLM interaction produces SUCCESS status."""
        invocation_id = uuid4()
        execution_id = uuid4()
        request_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STANDARD,
            model_name="gpt-4o",
            status=LLMInteractionStatus.SUCCESS,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            request_id=request_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.LLM_INTERACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "llm_call"
        assert result.event_message == "LLM interaction completed (standard)"
        assert result.source_component == "syntara.agent_orchestrator.agents.generic"
        assert result.actor_id == test_user.id
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == test_user.username
        assert result.execution_id == execution_id
        assert result.resource_urn == f"urn:syntara:invocation:{invocation_id}"

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "llm_interaction"
        assert result.structured_data.interaction_type == "standard"
        assert result.structured_data.model_name == "gpt-4o"
        assert result.structured_data.status == "success"
        assert result.structured_data.request_id == request_id
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    def test_successful_structured_output_interaction(self) -> None:
        """Successful structured output interaction produces SUCCESS status."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STRUCTURED_OUTPUT,
            model_name="claude-3-5-sonnet",
            status=LLMInteractionStatus.SUCCESS,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            response_schema_provided=True,
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_message == "LLM interaction completed (structured_output)"
        assert result.structured_data.interaction_type == "structured_output"
        assert result.structured_data.response_schema_provided is True

    def test_successful_extraction_interaction(self) -> None:
        """Successful extraction interaction produces SUCCESS status."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.EXTRACTION,
            model_name="gpt-4o-mini",
            status=LLMInteractionStatus.SUCCESS,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.event_message == "LLM interaction completed (extraction)"
        assert result.structured_data.interaction_type == "extraction"

    async def test_error_interaction(self, test_user: User) -> None:
        """Error LLM interaction produces ERROR severity with error details."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STANDARD,
            model_name="gpt-4o",
            status=LLMInteractionStatus.ERROR,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(
                actor_id=test_user.id, actor_username=test_user.username, actor_type=PrincipalType.USER
            ),
            error_type="RateLimitError",
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.event_message == "LLM interaction failed (standard)"
        assert result.structured_data.error_type == "RateLimitError"
        assert result.structured_data.error_message == "Look at the Operational Logs for full diagnosis"

    def test_empty_response_interaction(self) -> None:
        """Empty response LLM interaction produces WARNING severity."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STRUCTURED_OUTPUT,
            model_name="claude-3-5-sonnet",
            status=LLMInteractionStatus.EMPTY_RESPONSE,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_message == "LLM returned empty response (structured_output)"
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None

    def test_tool_usage_fields_included(self) -> None:
        """Tool usage fields (tools_available, tool_calls_made) are included."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STANDARD,
            model_name="gpt-4o",
            status=LLMInteractionStatus.SUCCESS,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            tools_available=5,
            tool_calls_made=2,
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.structured_data.tools_available == 5
        assert result.structured_data.tool_calls_made == 2

    def test_tool_fields_optional(self) -> None:
        """Tool usage fields are optional."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STANDARD,
            model_name="gpt-4o",
            status=LLMInteractionStatus.SUCCESS,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.structured_data.tools_available is None
        assert result.structured_data.tool_calls_made is None

    def test_response_schema_provided_default(self) -> None:
        """response_schema_provided defaults to False."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STANDARD,
            model_name="gpt-4o",
            status=LLMInteractionStatus.SUCCESS,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.structured_data.response_schema_provided is False

    def test_fallback_strategy_included(self) -> None:
        """Fallback strategy is included when provided."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STRUCTURED_OUTPUT,
            model_name="claude-3-5-sonnet",
            status=LLMInteractionStatus.SUCCESS,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            fallback_strategy_used="retry_with_simpler_schema",
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.structured_data.fallback_strategy_used == "retry_with_simpler_schema"

    def test_fallback_strategy_optional(self) -> None:
        """Fallback strategy is optional."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STANDARD,
            model_name="gpt-4o",
            status=LLMInteractionStatus.SUCCESS,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.structured_data.fallback_strategy_used is None

    def test_invocation_id_included(self) -> None:
        """Invocation ID is included in structured_data when provided."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STANDARD,
            model_name="gpt-4o",
            status=LLMInteractionStatus.SUCCESS,
            session_id="session_abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.execution_id == execution_id
        assert result.structured_data.invocation_id == invocation_id

    def test_no_actor_context(self) -> None:
        """Event without actor_context handles None gracefully."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STANDARD,
            model_name="gpt-4o",
            status=LLMInteractionStatus.SUCCESS,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=None,
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.actor_id is None
        assert result.actor_username is None
        assert result.actor_type is None

    def test_zero_tools_available(self) -> None:
        """Zero tools available is preserved."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STANDARD,
            model_name="gpt-4o",
            status=LLMInteractionStatus.SUCCESS,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            tools_available=0,
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.structured_data.tools_available == 0

    def test_zero_tool_calls_made(self) -> None:
        """Zero tool calls made is preserved."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STANDARD,
            model_name="gpt-4o",
            status=LLMInteractionStatus.SUCCESS,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            tool_calls_made=0,
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.structured_data.tool_calls_made == 0

    def test_error_without_explicit_error_type(self) -> None:
        """Error status without explicit error_type still produces error event."""
        invocation_id = uuid4()
        execution_id = uuid4()
        event = LLMInteractionEvent(
            interaction_type=LLMInteractionType.STANDARD,
            model_name="gpt-4o",
            status=LLMInteractionStatus.ERROR,
            session_id="session-abc",
            invocation_id=invocation_id,
            execution_id=execution_id,
            actor_context=AuditActorContext(),
            error_type=None,
        )

        handler = LLMInteractionHandler()
        result = handler.handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.structured_data.error_type is None
        assert result.structured_data.error_message is None
