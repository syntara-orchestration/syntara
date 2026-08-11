"""Unit tests for the GET /invocations/{invocation_id}/trace endpoint logic."""

from typing import Any
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.models.invocation import InvocationStatus, InvocationTraceRead


def _build_invocation(
    *,
    result: dict[str, Any] | None = None,
    trace_events: list[dict[str, Any]] | None = None,
    model_name: str | None = None,
    status: InvocationStatus = InvocationStatus.COMPLETED,
) -> object:
    """Build a minimal mock invocation object."""

    class _Inv:
        pass

    inv = _Inv()
    inv.id = uuid4()  # type: ignore[attr-defined]
    inv.status = status  # type: ignore[attr-defined]
    inv.result = result  # type: ignore[attr-defined]
    inv.trace_events = trace_events  # type: ignore[attr-defined]
    inv.model_name = model_name  # type: ignore[attr-defined]
    return inv


def _extract_trace(invocation) -> InvocationTraceRead:
    """Replicate the trace extraction logic from router.get_invocation_trace."""
    agent_trace = None
    if isinstance(invocation.result, dict):
        agent_trace = invocation.result.get("agent_trace")
    if agent_trace is None and invocation.trace_events:
        agent_trace = {
            "model": invocation.model_name or "unknown",
            "total_tokens": sum(t for s in invocation.trace_events if isinstance(t := s.get("tokens"), int)),
            "total_duration_ms": sum(t for s in invocation.trace_events if isinstance(t := s.get("duration_ms"), int)),
            "steps": invocation.trace_events,
        }
    return InvocationTraceRead(
        invocation_id=invocation.id,
        status=invocation.status,
        agent_trace=agent_trace,
    )


class TestTraceEndpointPrimaryPath:
    """Tests for the primary path: agent_trace in result."""

    def test_returns_trace_from_result(self):
        trace_data = {
            "model": "anthropic/claude-haiku-4.5",
            "total_tokens": 317,
            "total_duration_ms": 8915,
            "steps": [{"type": "reasoning", "content": "Analyzing..."}],
        }
        inv = _build_invocation(result={"agent_trace": trace_data})
        read = _extract_trace(inv)

        assert read.agent_trace == trace_data
        assert read.status == InvocationStatus.COMPLETED

    def test_prefers_result_over_trace_events(self):
        result_trace = {"model": "from-result", "total_tokens": 100, "total_duration_ms": 500, "steps": []}
        column_events = [{"type": "reasoning", "tokens": 50, "duration_ms": 200}]
        inv = _build_invocation(result={"agent_trace": result_trace}, trace_events=column_events)
        read = _extract_trace(inv)

        assert read.agent_trace["model"] == "from-result"

    def test_none_when_no_trace_data(self):
        inv = _build_invocation(result={"content": "hello"})
        read = _extract_trace(inv)

        assert read.agent_trace is None


class TestTraceEndpointFallbackPath:
    """Tests for the fallback path: trace_events column only."""

    def test_builds_trace_from_column(self):
        events = [
            {"type": "reasoning", "tokens": 50, "duration_ms": 400},
            {"type": "tool_call", "tokens": 20},
            {"type": "tool_result", "duration_ms": 100},
        ]
        inv = _build_invocation(result=None, trace_events=events, model_name="test-model")
        read = _extract_trace(inv)

        assert read.agent_trace is not None
        assert read.agent_trace["model"] == "test-model"
        assert read.agent_trace["total_tokens"] == 70
        assert read.agent_trace["total_duration_ms"] == 500
        assert read.agent_trace["steps"] == events

    def test_defaults_model_to_unknown(self):
        events = [{"type": "reasoning", "tokens": 10, "duration_ms": 100}]
        inv = _build_invocation(result=None, trace_events=events, model_name=None)
        read = _extract_trace(inv)

        assert read.agent_trace["model"] == "unknown"


class TestTraceWalrusExpressions:
    """Tests for the walrus-operator token/duration summation with mixed types."""

    @pytest.mark.parametrize(
        ("events", "expected_tokens", "expected_duration"),
        [
            ([{"tokens": 10, "duration_ms": 100}, {"tokens": 20, "duration_ms": 200}], 30, 300),
            ([{"tokens": None, "duration_ms": 100}, {"tokens": 20}], 20, 100),
            ([{"tokens": "12", "duration_ms": "fast"}], 0, 0),
            ([{}, {"tokens": 5}], 5, 0),
        ],
        ids=["normal", "none-and-missing", "string-values", "empty-steps"],
    )
    def test_sums_correctly_with_mixed_values(self, events, expected_tokens, expected_duration):
        inv = _build_invocation(result=None, trace_events=events, model_name="m")
        read = _extract_trace(inv)

        assert read.agent_trace["total_tokens"] == expected_tokens
        assert read.agent_trace["total_duration_ms"] == expected_duration

    def test_empty_trace_events_returns_none(self):
        inv = _build_invocation(result=None, trace_events=[], model_name="m")
        read = _extract_trace(inv)

        assert read.agent_trace is None
