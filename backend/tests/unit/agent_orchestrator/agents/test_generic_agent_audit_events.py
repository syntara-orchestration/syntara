"""Unit tests for GenericAgent audit event dispatch.

Verifies that GenericAgent emits the expected audit events during execution:
- AgentExecutionEvent (STARTED, COMPLETED, FAILED)
- LLMInteractionEvent (SUCCESS, EMPTY_RESPONSE, ERROR for standard/structured_output/extraction)
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from syntara.agent_orchestrator.agents.generic_agent import GenericAgent
from syntara.agent_orchestrator.audit.agent_execution import (
    AgentExecutionEvent,
    AgentExecutionHandler,
)
from syntara.agent_orchestrator.audit.llm_interaction import (
    LLMInteractionEvent,
    LLMInteractionHandler,
    LLMInteractionStatus,
    LLMInteractionType,
)
from syntara.agent_orchestrator.exceptions import EmptyLLMResponseError
from syntara.agent_orchestrator.models.agent_state import AgentState
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.emitter import AuditActorContext
from syntara.audit.events.function_execution import FunctionExecutionEvent, FunctionExecutionHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventStatus
from syntara.audit.sanitization import REDACTED


def _make_agent_state(**overrides: object) -> AgentState:
    """Build a minimal AgentState for testing."""
    defaults: AgentState = {
        "messages": [],
        "prompt": "test prompt",
        "original_prompt": "test prompt",
        "session_id": "sess-1",
        "invocation_id": uuid4(),
        "actor_context": AuditActorContext(),
        "current_agent": "generic_agent",
        "context_package": None,
        "metadata": None,
        "result": None,
        "llm_token_usage_log": [],
    }
    state = defaults.copy()
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


class TestGenericAgentExecutionEvents:
    """Tests for AgentExecutionEvent dispatch during _execute()."""

    def setup_method(self) -> None:
        """Register audit event handlers for GenericAgent tests."""
        AuditEventDispatcher.register(
            {
                AgentExecutionEvent: AgentExecutionHandler(),
                LLMInteractionEvent: LLMInteractionHandler(),
                FunctionExecutionEvent: FunctionExecutionHandler(),
            }
        )

    @pytest.mark.asyncio
    async def test_execute_emits_started_and_completed_events(self) -> None:
        """Successful execution emits STARTED and COMPLETED AgentExecutionEvents."""
        session_id = "sess-123"
        invocation_id = uuid4()
        execution_id = uuid4()
        request_id = uuid4()

        state = _make_agent_state(
            session_id=session_id,
            invocation_id=invocation_id,
            execution_id=execution_id,
            request_id=request_id,
        )

        # Mock LLM to return valid response
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(
            return_value=AIMessage(content="test response", response_metadata={})
        )
        mock_llm.model_name = "test-model"

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch("syntara.metrics.instrumentation.record_llm_call", side_effect=lambda _, fn, **__: fn()),
        ):
            await agent._execute(state)

        # Verify events: STARTED, SUCCESS (LLM), COMPLETED, plus @audit decorator event
        assert mock_do_emit.call_count == 3
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]

        # Filter to AgentExecutionEvents only (by event_action pattern)
        execution_events = [e for e in events if e.event_action in ["agent_started", "agent_completed"]]
        assert len(execution_events) == 2

        # Event 1: STARTED
        assert execution_events[0].event_action == "agent_started"
        assert execution_events[0].event_category == EventCategory.AGENT_INTERACTION
        assert execution_events[0].event_status == EventStatus.SUCCESS
        assert execution_events[0].structured_data.status == "started"  # type: ignore[attr-defined]
        assert execution_events[0].structured_data.agent_type == "generic_agent"  # type: ignore[attr-defined]
        assert execution_events[0].structured_data.session_id == REDACTED  # type: ignore[attr-defined]
        assert execution_events[0].structured_data.invocation_id == str(invocation_id)  # type: ignore[attr-defined]
        assert execution_events[0].execution_id == execution_id
        assert execution_events[0].structured_data.request_id == str(request_id)  # type: ignore[attr-defined]
        assert execution_events[0].resource_urn == f"urn:syntara:invocation:{invocation_id}"
        assert execution_events[0].resource_name == "generic_agent"

        # Event 2: COMPLETED
        assert execution_events[1].event_action == "agent_completed"
        assert execution_events[1].structured_data.status == "completed"  # type: ignore[attr-defined]
        assert execution_events[1].execution_id == execution_id
        assert execution_events[1].structured_data.request_id == str(request_id)  # type: ignore[attr-defined]
        assert execution_events[1].structured_data.agent_type == "generic_agent"  # type: ignore[attr-defined]
        assert execution_events[1].resource_urn == f"urn:syntara:invocation:{invocation_id}"
        assert execution_events[1].resource_name == "generic_agent"

    @pytest.mark.asyncio
    async def test_execute_emits_failed_event_on_exception(self) -> None:
        """Failed execution emits STARTED and FAILED AgentExecutionEvents."""
        session_id = "sess-456"
        invocation_id = uuid4()

        state = _make_agent_state(session_id=session_id, invocation_id=invocation_id)

        # Mock LLM to raise exception
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(side_effect=ValueError("LLM error"))
        mock_llm.model_name = "test-model"

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch("syntara.metrics.instrumentation.record_llm_call", side_effect=lambda _, fn, **__: fn()),
            pytest.raises(ValueError),
        ):
            await agent._execute(state)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        execution_events = [e for e in events if e.event_action in ["agent_started", "agent_failed"]]

        # Should have STARTED and FAILED
        assert len(execution_events) == 2
        assert execution_events[0].structured_data.status == "started"  # type: ignore[attr-defined]
        assert execution_events[1].structured_data.status == "failed"  # type: ignore[attr-defined]
        assert execution_events[1].structured_data.error_type == "ValueError"


class TestGenericAgentLLMInteractionEvents:
    """Tests for LLMInteractionEvent dispatch during LLM calls."""

    def setup_method(self) -> None:
        """Register audit event handlers for LLM interaction tests."""
        AuditEventDispatcher.register(
            {
                LLMInteractionEvent: LLMInteractionHandler(),
            }
        )

    @pytest.mark.asyncio
    async def test_execute_standard_emits_success_event(self) -> None:
        """Standard LLM call emits SUCCESS LLMInteractionEvent."""
        session_id = "sess-llm-standard"
        invocation_id = uuid4()
        execution_id = uuid4()

        state = _make_agent_state(session_id=session_id, invocation_id=invocation_id, execution_id=execution_id)

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(
            return_value=AIMessage(content="answer", response_metadata={})
        )
        mock_llm.model_name = "test-model"

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch("syntara.metrics.instrumentation.record_llm_call", side_effect=lambda _, fn, **__: fn()),
        ):
            await agent._execute_standard(state)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        llm_events = [e for e in events if e.event_action == "llm_call"]

        assert len(llm_events) == 1
        assert llm_events[0].structured_data.interaction_type == LLMInteractionType.STANDARD  # type: ignore[attr-defined]
        assert llm_events[0].structured_data.status == LLMInteractionStatus.SUCCESS  # type: ignore[attr-defined]
        assert llm_events[0].structured_data.model_name == "test-model"  # type: ignore[attr-defined]
        # Verify session_id and resource_urn
        assert llm_events[0].structured_data.session_id == "[REDACTED]"  # type: ignore[attr-defined]
        assert llm_events[0].structured_data.invocation_id == str(invocation_id)  # type: ignore[attr-defined]
        assert llm_events[0].resource_urn == f"urn:syntara:invocation:{invocation_id}"
        # Without metadata, activity_name should be None
        assert llm_events[0].resource_name is None

    @pytest.mark.asyncio
    async def test_execute_standard_emits_empty_response_event(self) -> None:
        """Empty LLM response emits EMPTY_RESPONSE LLMInteractionEvent."""
        session_id = "sess-llm-empty"
        invocation_id = uuid4()

        state = _make_agent_state(session_id=session_id, invocation_id=invocation_id)

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=AIMessage(content="", response_metadata={}))
        mock_llm.model_name = "test-model"

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch("syntara.metrics.instrumentation.record_llm_call", side_effect=lambda _, fn, **__: fn()),
            pytest.raises(EmptyLLMResponseError),
        ):
            await agent._execute_standard(state)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        llm_events = [e for e in events if e.event_action == "llm_call"]

        assert len(llm_events) == 1
        assert llm_events[0].structured_data.status == LLMInteractionStatus.EMPTY_RESPONSE  # type: ignore[attr-defined]
        assert llm_events[0].structured_data.error_type is None
        assert llm_events[0].structured_data.error_message is None
        # Verify session_id and resource_urn
        assert llm_events[0].structured_data.session_id == "[REDACTED]"  # type: ignore[attr-defined]
        assert llm_events[0].resource_urn == f"urn:syntara:invocation:{invocation_id}"

    @pytest.mark.asyncio
    async def test_execute_structured_emits_success_event(self) -> None:
        """Structured output emits SUCCESS LLMInteractionEvent."""
        session_id = "sess-llm-struct"
        invocation_id = uuid4()
        execution_id = uuid4()

        state = _make_agent_state(session_id=session_id, invocation_id=invocation_id, execution_id=execution_id)
        response_schema: dict[str, Any] = {"type": "object"}

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value={"result": "structured"})
        mock_llm.model_name = "test-model"

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch("syntara.metrics.instrumentation.record_llm_call", side_effect=lambda _, fn, **__: fn()),
        ):
            await agent._execute_structured(state, response_schema)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        llm_events = [e for e in events if e.event_action == "llm_call"]

        assert len(llm_events) == 1
        assert llm_events[0].structured_data.interaction_type == LLMInteractionType.STRUCTURED_OUTPUT  # type: ignore[attr-defined]
        assert llm_events[0].structured_data.status == LLMInteractionStatus.SUCCESS  # type: ignore[attr-defined]
        assert llm_events[0].structured_data.response_schema_provided is True  # type: ignore[attr-defined]
        # Verify session_id and resource_urn
        assert llm_events[0].structured_data.session_id == "[REDACTED]"  # type: ignore[attr-defined]
        assert llm_events[0].resource_urn == f"urn:syntara:invocation:{invocation_id}"

    @pytest.mark.asyncio
    async def test_execute_structured_emits_error_event_on_failure(self) -> None:
        """Structured output failure emits ERROR LLMInteractionEvent."""
        invocation_id = uuid4()

        state = _make_agent_state(invocation_id=invocation_id)
        response_schema: dict[str, Any] = {"type": "object"}

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(side_effect=ValueError("Schema error"))
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(
            return_value=AIMessage(content="fallback", response_metadata={})
        )
        mock_llm.model_name = "test-model"

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch("syntara.metrics.instrumentation.record_llm_call", side_effect=lambda _, fn, **__: fn()),
        ):
            await agent._execute_structured(state, response_schema)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        llm_events = [e for e in events if e.event_action == "llm_call"]

        # Should have ERROR (structured_output) + SUCCESS (standard fallback)
        assert len(llm_events) == 2
        error_event = next(
            e
            for e in llm_events
            if e.structured_data.interaction_type == LLMInteractionType.STRUCTURED_OUTPUT  # type: ignore[attr-defined]
        )
        assert error_event.structured_data.status == LLMInteractionStatus.ERROR  # type: ignore[attr-defined]
        assert error_event.structured_data.error_type == "ValueError"

    @pytest.mark.asyncio
    async def test_execute_structured_parse_none_emits_error_then_standard_success(self) -> None:
        """Soft parse failure (include_raw) emits ERROR then falls back to standard SUCCESS."""
        invocation_id = uuid4()

        state = _make_agent_state(invocation_id=invocation_id)
        response_schema: dict[str, Any] = {"type": "object"}

        raw = AIMessage(
            content="not-json",
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value={"raw": raw, "parsed": None, "parsing_error": "parse failed"}
        )
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(
            return_value=AIMessage(content="fallback", response_metadata={})
        )
        mock_llm.model_name = "test-model"

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch("syntara.metrics.instrumentation.record_llm_call", side_effect=lambda _, fn, **__: fn()),
        ):
            await agent._execute_structured(state, response_schema)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        llm_events = [e for e in events if e.event_action == "llm_call"]

        assert len(llm_events) == 2
        structured_event = next(
            e
            for e in llm_events
            if e.structured_data.interaction_type == LLMInteractionType.STRUCTURED_OUTPUT  # type: ignore[attr-defined]
        )
        assert structured_event.structured_data.status == LLMInteractionStatus.ERROR  # type: ignore[attr-defined]
        assert structured_event.structured_data.error_type == "StructuredOutputParseError"
        standard_event = next(
            e
            for e in llm_events
            if e.structured_data.interaction_type == LLMInteractionType.STANDARD  # type: ignore[attr-defined]
        )
        assert standard_event.structured_data.status == LLMInteractionStatus.SUCCESS  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_extract_structured_output_emits_success_event(self) -> None:
        """Extraction step emits SUCCESS LLMInteractionEvent."""
        invocation_id = uuid4()
        execution_id = uuid4()

        state = _make_agent_state(
            invocation_id=invocation_id,
            execution_id=execution_id,
            result={"content": "raw text"},
        )
        response_schema: dict[str, Any] = {"type": "object"}

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value={"extracted": "data"})
        mock_llm.model_name = "test-model"

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch("syntara.metrics.instrumentation.record_llm_call", side_effect=lambda _, fn, **__: fn()),
        ):
            await agent._extract_structured_output(state, response_schema)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        llm_events = [e for e in events if e.event_action == "llm_call"]

        assert len(llm_events) == 1
        assert llm_events[0].structured_data.interaction_type == LLMInteractionType.EXTRACTION  # type: ignore[attr-defined]
        assert llm_events[0].structured_data.status == LLMInteractionStatus.SUCCESS  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_extract_structured_output_emits_error_event_on_failure(self) -> None:
        """Extraction failure emits ERROR LLMInteractionEvent."""
        invocation_id = uuid4()

        state = _make_agent_state(invocation_id=invocation_id, result={"content": "text"})
        response_schema: dict[str, Any] = {"type": "object"}

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(side_effect=RuntimeError("Extraction failed"))
        mock_llm.model_name = "test-model"

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch("syntara.metrics.instrumentation.record_llm_call", side_effect=lambda _, fn, **__: fn()),
        ):
            await agent._extract_structured_output(state, response_schema)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        llm_events = [e for e in events if e.event_action == "llm_call"]

        assert len(llm_events) == 1
        assert llm_events[0].structured_data.status == LLMInteractionStatus.ERROR  # type: ignore[attr-defined]
        assert llm_events[0].structured_data.error_type == "RuntimeError"

    @pytest.mark.asyncio
    async def test_extract_structured_output_parse_none_does_not_emit_success(self) -> None:
        """Parse-None extraction keeps raw text and must not emit SUCCESS/native."""
        invocation_id = uuid4()

        state = _make_agent_state(invocation_id=invocation_id, result={"content": "raw text"})
        response_schema: dict[str, Any] = {"type": "object"}

        raw = AIMessage(
            content="not-json",
            usage_metadata={"input_tokens": 40, "output_tokens": 15, "total_tokens": 55},
        )
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value={"raw": raw, "parsed": None, "parsing_error": "parse failed"}
        )
        mock_llm.model_name = "test-model"

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch("syntara.metrics.instrumentation.record_llm_call", side_effect=lambda _, fn, **__: fn()),
        ):
            result_state = await agent._extract_structured_output(state, response_schema)

        assert result_state["result"] is not None
        assert result_state["result"]["content"] == "raw text"
        assert result_state["result"]["structured_output_metadata"]["fallback_strategy_used"] == "none"

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        llm_events = [e for e in events if e.event_action == "llm_call"]
        assert llm_events == []

    @pytest.mark.asyncio
    async def test_llm_interaction_includes_activity_context_from_metadata(self) -> None:
        """LLMInteractionEvent includes activity_id and activity_name from state metadata."""
        session_id = "sess-with-activity"
        invocation_id = uuid4()
        execution_id = uuid4()

        # State with metadata containing activity context
        state = _make_agent_state(
            session_id=session_id,
            invocation_id=invocation_id,
            execution_id=execution_id,
            metadata={"activity_id": "activity-123", "activity_name": "agentic_v2"},
        )

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value.ainvoke = AsyncMock(
            return_value=AIMessage(content="response with activity", response_metadata={})
        )
        mock_llm.model_name = "test-model"

        agent = GenericAgent(llm=mock_llm, available_tools=[])

        with (
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch("syntara.metrics.instrumentation.record_llm_call", side_effect=lambda _, fn, **__: fn()),
        ):
            await agent._execute_standard(state)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        llm_events = [e for e in events if e.event_action == "llm_call"]

        assert len(llm_events) == 1
        assert llm_events[0].structured_data.status == LLMInteractionStatus.SUCCESS  # type: ignore[attr-defined]
        assert llm_events[0].resource_urn == f"urn:syntara:invocation:{invocation_id}"
        # Verify activity context from metadata (stored in AuditEvent, not structured_data)
        assert llm_events[0].activity_id == "activity-123"
        assert llm_events[0].resource_name == "agentic_v2"
