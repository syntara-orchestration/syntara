"""Unit tests for agent metrics instrumentation.

Validates that agent routing and execution lifecycle events produce the
expected metrics records (FR-018 through FR-020).
"""

import copy
from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from prometheus_client import CollectorRegistry

from syntara.agent_orchestrator.agents.base_agent import BaseAgent
from syntara.agent_orchestrator.agents.orchestrator_agent import OrchestratorAgent
from syntara.agent_orchestrator.constants import AgentRoutes
from syntara.agent_orchestrator.exceptions import AgentOrchestratorError
from syntara.agent_orchestrator.models.agent_state import AgentState
from syntara.audit.emitter import AuditActorContext
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import MetricType
from tests.fixtures.settings import FakeSettingsCache

INVOCATION_ID = uuid4()


@pytest.fixture
def recorder() -> MetricsRecorder:
    """Fresh MetricsRecorder with an isolated Prometheus registry."""
    return MetricsRecorder(
        retention_seconds=3600,
        max_records=10_000,
        prometheus_registry=CollectorRegistry(),
    )


def _make_agent_state(**overrides: object) -> AgentState:
    """Build a minimal AgentState dict for testing."""
    defaults: AgentState = {
        "messages": [],
        "prompt": "hello world",
        "original_prompt": "hello world",
        "session_id": "sess-1",
        "invocation_id": INVOCATION_ID,
        "actor_context": AuditActorContext(),
        "current_agent": AgentRoutes.ORCHESTRATOR,
        "context_package": None,
        "metadata": None,
        "result": None,
        "llm_token_usage_log": [],
    }
    state = copy.deepcopy(defaults)
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


# =============================================================================
# Agent routing metrics (OrchestratorAgent._route_request)
# =============================================================================


class TestAgentRoutingMetrics:
    """Tests for agent routing duration recording."""

    @pytest.fixture(autouse=True)
    def _mock_runtime_settings(  # type: ignore[misc]
        self, override_runtime_settings: Callable[..., AbstractContextManager[FakeSettingsCache]]
    ) -> None:
        """Auto-mock get_runtime_settings for orchestrator tests."""
        with override_runtime_settings():
            yield

    def test_route_request_records_duration(self, recorder: MetricsRecorder) -> None:
        """_route_request records an AGENT_ROUTING_DURATION metric."""
        context_manager = AsyncMock()
        agent = OrchestratorAgent(context_manager_planner=context_manager)
        state = _make_agent_state()

        with patch(
            "syntara.agent_orchestrator.agents.orchestrator_agent.get_metrics_recorder",
            return_value=recorder,
        ):
            result = agent._route_request(state)

        results = list(recorder.query(metric_types={MetricType.AGENT_ROUTING_DURATION}))
        assert len(results) == 1
        assert results[0].value >= 0
        assert results[0].unit == "ms"
        assert results[0].labels["invocation_id"] == str(INVOCATION_ID)
        assert results[0].labels["target_agent"] == AgentRoutes.GENERIC_AGENT
        assert result["current_agent"] == AgentRoutes.GENERIC_AGENT


# =============================================================================
# Agent node execution metrics (BaseAgent.execute_as_node)
# =============================================================================


class _StubAgent(BaseAgent):
    """Concrete stub of BaseAgent for testing."""

    def __init__(self, *, should_fail: bool = False) -> None:
        super().__init__()
        self.should_fail = should_fail

    async def _execute(self, state: AgentState) -> AgentState:
        if self.should_fail:
            msg = "boom"
            raise ValueError(msg)
        return state


class TestAgentNodeExecutionMetrics:
    """Tests for BaseAgent.execute_as_node timing."""

    @pytest.mark.asyncio
    async def test_success_records_duration(self, recorder: MetricsRecorder) -> None:
        """Successful agent execution records AGENT_INVOCATION_DURATION with status=success."""
        agent = _StubAgent(should_fail=False)
        state = _make_agent_state()

        with patch(
            "syntara.agent_orchestrator.agents.base_agent.get_metrics_recorder",
            return_value=recorder,
        ):
            await agent.execute_as_node(state)

        results = list(recorder.query(metric_types={MetricType.AGENT_INVOCATION_DURATION}))
        assert len(results) == 1
        assert results[0].labels["status"] == "success"
        assert results[0].labels["agent_type"] == "_StubAgent"
        assert results[0].value >= 0

    @pytest.mark.asyncio
    async def test_failure_records_duration(self, recorder: MetricsRecorder) -> None:
        """Failed agent execution records AGENT_INVOCATION_DURATION with status=error."""
        agent = _StubAgent(should_fail=True)
        state = _make_agent_state()

        with (
            patch(
                "syntara.agent_orchestrator.agents.base_agent.get_metrics_recorder",
                return_value=recorder,
            ),
            pytest.raises(AgentOrchestratorError),
        ):
            await agent.execute_as_node(state)

        results = list(recorder.query(metric_types={MetricType.AGENT_INVOCATION_DURATION}))
        assert len(results) == 1
        assert results[0].labels["status"] == "error"
        assert results[0].labels["agent_type"] == "_StubAgent"
