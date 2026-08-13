"""Unit tests for OrchestratorAgent audit event dispatch.

Verifies that OrchestratorAgent emits the expected audit events during execution:
- AgentExecutionEvent (STARTED, COMPLETED, FAILED)
- ContextIntegrationEvent (SUCCESS, TIMEOUT, FALLBACK)
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.agents.orchestrator_agent import OrchestratorAgent
from syntara.agent_orchestrator.audit.agent_execution import (
    AgentExecutionEvent,
    AgentExecutionHandler,
)
from syntara.agent_orchestrator.audit.context_integration import (
    ContextIntegrationEvent,
    ContextIntegrationHandler,
)
from syntara.agent_orchestrator.context_manager.models import ContextPackage
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
        "current_agent": "orchestrator",
        "context_package": None,
        "metadata": None,
        "result": None,
        "llm_token_usage_log": [],
    }
    state = defaults.copy()
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


class TestOrchestratorAgentExecutionEvents:
    """Tests for AgentExecutionEvent dispatch during execute()."""

    def setup_method(self) -> None:
        """Register audit event handlers for OrchestratorAgent tests."""
        AuditEventDispatcher.register(
            {
                AgentExecutionEvent: AgentExecutionHandler(),
                ContextIntegrationEvent: ContextIntegrationHandler(),
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

        # Mock context manager to return valid package
        mock_context_manager = AsyncMock()
        mock_context_manager.plan_request = AsyncMock(
            return_value=ContextPackage(
                id="pkg-1",
                grounding_score=0.85,
                citations=[],
                payload={"context": "test context"},
            )
        )

        # Mock settings to return timeout
        mock_settings = MagicMock()
        mock_settings.get_int = AsyncMock(return_value=30)

        with patch(
            "syntara.agent_orchestrator.agents.orchestrator_agent.get_runtime_settings", return_value=mock_settings
        ):
            agent = OrchestratorAgent(context_manager_planner=mock_context_manager)

        with patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit:
            await agent.execute(state)

        # Verify events: STARTED, SUCCESS (context), COMPLETED, plus @audit decorator event
        assert mock_do_emit.call_count == 3
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]

        # Filter to AgentExecutionEvents (by event_action pattern)
        execution_events = [e for e in events if e.event_action in ["agent_started", "agent_completed"]]
        assert len(execution_events) == 2

        # Event 1: STARTED
        assert execution_events[0].event_action == "agent_started"
        assert execution_events[0].event_category == EventCategory.AGENT_INTERACTION
        assert execution_events[0].event_status == EventStatus.SUCCESS
        assert execution_events[0].structured_data.status == "started"  # type: ignore[attr-defined]
        assert execution_events[0].structured_data.agent_type == "orchestrator"  # type: ignore[attr-defined]
        assert execution_events[0].structured_data.session_id == REDACTED  # type: ignore[attr-defined]
        assert execution_events[0].execution_id == execution_id
        assert execution_events[0].structured_data.request_id == str(request_id)  # type: ignore[attr-defined]

        # Event 2: COMPLETED
        assert execution_events[1].event_action == "agent_completed"
        assert execution_events[1].structured_data.status == "completed"  # type: ignore[attr-defined]
        assert execution_events[1].structured_data.context_applied is True  # type: ignore[attr-defined]
        assert execution_events[1].structured_data.grounding_score == 0.85  # type: ignore[attr-defined]
        assert execution_events[1].structured_data.routed_to_agent is not None  # type: ignore[attr-defined]
        assert execution_events[1].execution_id == execution_id
        assert execution_events[1].structured_data.request_id == str(request_id)  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_execute_emits_failed_event_on_exception(self) -> None:
        """Failed execution emits STARTED and FAILED AgentExecutionEvents.

        Note: Context integration errors are handled gracefully (fallback to original prompt),
        but other exceptions during routing still cause agent failure.
        """
        session_id = "sess-456"
        invocation_id = uuid4()

        state = _make_agent_state(session_id=session_id, invocation_id=invocation_id)

        # Mock context manager to succeed, then mock _route_request to fail
        mock_context_manager = AsyncMock()
        mock_context_manager.plan_request = AsyncMock(
            return_value=ContextPackage(
                id="pkg-1",
                grounding_score=0.5,
                citations=[],
                payload={},
            )
        )

        mock_settings = MagicMock()
        mock_settings.get_int = AsyncMock(return_value=30)

        with (
            patch(
                "syntara.agent_orchestrator.agents.orchestrator_agent.get_runtime_settings", return_value=mock_settings
            ),
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
            patch.object(OrchestratorAgent, "_route_request", side_effect=RuntimeError("Routing error")),
            pytest.raises(RuntimeError),
        ):
            agent = OrchestratorAgent(context_manager_planner=mock_context_manager)
            await agent.execute(state)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        execution_events = [e for e in events if e.event_action in ["agent_started", "agent_failed"]]

        # Should have STARTED and FAILED
        assert len(execution_events) == 2
        assert execution_events[0].structured_data.status == "started"  # type: ignore[attr-defined]
        assert execution_events[1].structured_data.status == "failed"  # type: ignore[attr-defined]
        assert execution_events[1].structured_data.error_type == "RuntimeError"


class TestOrchestratorAgentContextIntegrationEvents:
    """Tests for ContextIntegrationEvent dispatch during _integrate_context()."""

    def setup_method(self) -> None:
        """Register audit event handlers for context integration tests."""
        AuditEventDispatcher.register(
            {
                ContextIntegrationEvent: ContextIntegrationHandler(),
            }
        )

    @pytest.mark.asyncio
    async def test_integrate_context_emits_success_event(self) -> None:
        """Successful context integration emits SUCCESS ContextIntegrationEvent."""
        session_id = "sess-789"
        invocation_id = uuid4()
        execution_id = uuid4()

        state = _make_agent_state(
            session_id=session_id,
            invocation_id=invocation_id,
            execution_id=execution_id,
            original_prompt="test query",
        )

        mock_context_manager = AsyncMock()
        mock_context_manager.plan_request = AsyncMock(
            return_value=ContextPackage(
                id="pkg-2",
                grounding_score=0.92,
                citations=["citation1", "citation2"],
                payload={"relevant": "context"},
            )
        )

        mock_settings = MagicMock()
        mock_settings.get_int = AsyncMock(return_value=30)

        with (
            patch(
                "syntara.agent_orchestrator.agents.orchestrator_agent.get_runtime_settings", return_value=mock_settings
            ),
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
        ):
            agent = OrchestratorAgent(context_manager_planner=mock_context_manager)
            result = await agent._integrate_context(state)

        # Verify SUCCESS event emitted
        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        context_events = [e for e in events if e.event_action == "context_integration"]

        assert len(context_events) == 1
        assert context_events[0].structured_data.status == "success"  # type: ignore[attr-defined]
        assert context_events[0].structured_data.grounding_score == 0.92  # type: ignore[attr-defined]
        assert context_events[0].structured_data.citations_count == 2  # type: ignore[attr-defined]
        assert context_events[0].structured_data.session_id == REDACTED  # type: ignore[attr-defined]

        # Verify state updated with context
        assert result["context_package"] is not None
        assert result["context_package"]["context_applied"] is True

    @pytest.mark.asyncio
    async def test_integrate_context_emits_timeout_event(self) -> None:
        """Context integration timeout emits TIMEOUT ContextIntegrationEvent."""
        import asyncio

        session_id = "sess-timeout"
        invocation_id = uuid4()

        state = _make_agent_state(session_id=session_id, invocation_id=invocation_id)

        # Mock context manager to timeout
        async def timeout_fn(*args: object, **kwargs: object) -> None:
            await asyncio.sleep(100)  # Longer than timeout

        mock_context_manager = AsyncMock()
        mock_context_manager.plan_request = timeout_fn

        mock_settings = MagicMock()
        mock_settings.get_int = AsyncMock(return_value=0.01)  # Very short timeout

        with (
            patch(
                "syntara.agent_orchestrator.agents.orchestrator_agent.get_runtime_settings", return_value=mock_settings
            ),
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
        ):
            agent = OrchestratorAgent(context_manager_planner=mock_context_manager)
            result = await agent._integrate_context(state)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        context_events = [e for e in events if e.event_action == "context_integration"]

        assert len(context_events) == 1
        assert context_events[0].structured_data.status == "timeout"  # type: ignore[attr-defined]
        assert context_events[0].structured_data.error_type is None
        assert context_events[0].structured_data.error_message is None

        # Verify graceful fallback - context_package is None
        assert result["context_package"] is None

    @pytest.mark.asyncio
    async def test_integrate_context_emits_fallback_event(self) -> None:
        """Context integration error emits FALLBACK ContextIntegrationEvent."""
        session_id = "sess-fallback"
        invocation_id = uuid4()
        execution_id = uuid4()

        state = _make_agent_state(
            session_id=session_id,
            invocation_id=invocation_id,
            execution_id=execution_id,
        )

        # Mock context manager to raise ConnectionError
        mock_context_manager = AsyncMock()
        mock_context_manager.plan_request = AsyncMock(side_effect=ConnectionError("Network error"))

        mock_settings = MagicMock()
        mock_settings.get_int = AsyncMock(return_value=30)

        with (
            patch(
                "syntara.agent_orchestrator.agents.orchestrator_agent.get_runtime_settings", return_value=mock_settings
            ),
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
        ):
            agent = OrchestratorAgent(context_manager_planner=mock_context_manager)
            result = await agent._integrate_context(state)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        context_events = [e for e in events if e.event_action == "context_integration"]

        assert len(context_events) == 1
        assert context_events[0].structured_data.status == "fallback"  # type: ignore[attr-defined]
        assert context_events[0].structured_data.error_type is None
        assert context_events[0].structured_data.error_message is None

        # Verify graceful fallback
        assert result["context_package"] is None

    @pytest.mark.asyncio
    async def test_context_integration_event_includes_context_identifiers(self) -> None:
        """ContextIntegrationEvent includes session_id, invocation_id, execution_id and resource_urn."""
        session_id = "sess-context-schema"
        invocation_id = uuid4()
        execution_id = uuid4()

        state = _make_agent_state(session_id=session_id, invocation_id=invocation_id, execution_id=execution_id)

        mock_context_manager = AsyncMock()
        mock_context_manager.plan_request = AsyncMock(
            return_value=ContextPackage(
                id="pkg-schema",
                grounding_score=0.9,
                citations=[],
                payload={},
            )
        )

        mock_settings = MagicMock()
        mock_settings.get_int = AsyncMock(return_value=30)

        with (
            patch(
                "syntara.agent_orchestrator.agents.orchestrator_agent.get_runtime_settings", return_value=mock_settings
            ),
            patch("syntara.audit.emitter._do_emit_audit_event") as mock_do_emit,
        ):
            agent = OrchestratorAgent(context_manager_planner=mock_context_manager)
            await agent._integrate_context(state)

        events: list[AuditEvent] = [call.args[0] for call in mock_do_emit.call_args_list]
        context_events = [e for e in events if e.event_action == "context_integration"]

        assert len(context_events) == 1
        # Verify session_id is redacted in structured_data
        assert context_events[0].structured_data.session_id == "[REDACTED]"  # type: ignore[attr-defined]
        # Verify invocation_id is included
        assert context_events[0].structured_data.invocation_id == str(invocation_id)  # type: ignore[attr-defined]
        # Verify execution_id is included
        assert context_events[0].execution_id == execution_id
        # Verify resource_urn
        assert context_events[0].resource_urn == f"urn:syntara:invocation:{invocation_id}"
