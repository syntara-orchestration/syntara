"""Unit tests for _TraceAccumulator in OrchestrationService."""

from typing import Any
from unittest.mock import MagicMock

from syntara.agent_orchestrator.services.orchestration_service import _TraceAccumulator


def _make_chat_stream_event(content: str, output_tokens: int = 0) -> dict[str, Any]:
    """Create a mock on_chat_model_stream event."""
    chunk = MagicMock()
    chunk.content = content
    if output_tokens:
        chunk.usage_metadata = {"output_tokens": output_tokens}
    else:
        chunk.usage_metadata = None
    return {"event": "on_chat_model_stream", "data": {"chunk": chunk}}


def _make_tool_start_event(
    tool_name: str, tool_input: dict[str, Any] | None = None, run_id: str | None = None
) -> dict[str, Any]:
    return {
        "event": "on_tool_start",
        "name": tool_name,
        "data": {"input": tool_input or {}},
        "run_id": run_id,
    }


def _make_tool_end_event(tool_name: str, tool_output: str = "", run_id: str | None = None) -> dict[str, Any]:
    output = MagicMock()
    output.content = tool_output
    return {
        "event": "on_tool_end",
        "name": tool_name,
        "data": {"output": output},
        "run_id": run_id,
    }


class TestTraceAccumulatorReasoningCoalescing:
    """Tests for delta coalescing into reasoning blocks."""

    def test_consecutive_deltas_coalesce_into_single_reasoning_step(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_chat_stream_event("Hello"))
        acc.accumulate(_make_chat_stream_event(" world"))
        acc.accumulate(_make_chat_stream_event("!"))

        result = acc.finalize(model_name="test-model")
        reasoning_steps = [s for s in result["steps"] if s["type"] == "reasoning"]
        assert len(reasoning_steps) == 1
        assert reasoning_steps[0]["content"] == "Hello world!"

    def test_empty_content_is_skipped(self) -> None:
        chunk = MagicMock()
        chunk.content = ""
        chunk.usage_metadata = None
        event = {"event": "on_chat_model_stream", "data": {"chunk": chunk}}

        acc = _TraceAccumulator()
        acc.accumulate(event)
        result = acc.finalize(model_name="test-model")
        reasoning_steps = [s for s in result["steps"] if s["type"] == "reasoning"]
        assert len(reasoning_steps) == 0

    def test_none_content_is_skipped(self) -> None:
        chunk = MagicMock()
        chunk.content = None
        chunk.usage_metadata = None
        event = {"event": "on_chat_model_stream", "data": {"chunk": chunk}}

        acc = _TraceAccumulator()
        acc.accumulate(event)
        result = acc.finalize(model_name="test-model")
        assert len(result["steps"]) == 0

    def test_reasoning_has_tokens_count(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_chat_stream_event("Hello", output_tokens=5))
        acc.accumulate(_make_chat_stream_event(" world", output_tokens=3))

        result = acc.finalize(model_name="test-model")
        reasoning = result["steps"][0]
        assert reasoning["tokens"] == 8


class TestTraceAccumulatorToolEvents:
    """Tests for tool call and tool result accumulation."""

    def test_tool_call_creates_step(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_tool_start_event("calculator", {"a": 5, "b": 3}))

        result = acc.finalize(model_name="test-model")
        tool_steps = [s for s in result["steps"] if s["type"] == "tool_call"]
        assert len(tool_steps) == 1
        assert tool_steps[0]["tool_name"] == "calculator"
        assert tool_steps[0]["tool_input"] == {"a": 5, "b": 3}

    def test_tool_result_creates_step(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_tool_start_event("calculator"))
        acc.accumulate(_make_tool_end_event("calculator", "8"))

        result = acc.finalize(model_name="test-model")
        result_steps = [s for s in result["steps"] if s["type"] == "tool_result"]
        assert len(result_steps) == 1
        assert result_steps[0]["tool_name"] == "calculator"
        assert result_steps[0]["tool_output"] == "8"

    def test_tool_result_has_duration_ms(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_tool_start_event("calculator"))
        acc.accumulate(_make_tool_end_event("calculator", "8"))

        result = acc.finalize(model_name="test-model")
        result_step = next(s for s in result["steps"] if s["type"] == "tool_result")
        assert "duration_ms" in result_step
        assert isinstance(result_step["duration_ms"], int)
        assert result_step["duration_ms"] >= 0

    def test_non_serializable_tool_input_is_stripped(self) -> None:
        acc = _TraceAccumulator()
        bad_input: dict[str, Any] = {"query": "SELECT *", "callback": MagicMock()}
        acc.accumulate(_make_tool_start_event("db_query", bad_input))

        result = acc.finalize(model_name="test-model")
        tool_step = next(s for s in result["steps"] if s["type"] == "tool_call")
        assert "query" in tool_step["tool_input"]
        assert "callback" not in tool_step["tool_input"]

    def test_tool_result_content_truncated_for_long_output(self) -> None:
        acc = _TraceAccumulator()
        long_output = "x" * 500
        acc.accumulate(_make_tool_start_event("search"))
        acc.accumulate(_make_tool_end_event("search", long_output))

        result = acc.finalize(model_name="test-model")
        result_step = next(s for s in result["steps"] if s["type"] == "tool_result")
        assert len(result_step["content"]) == 200
        assert result_step["tool_output"] == long_output

    def test_tool_output_truncated_when_exceeds_max_length(self) -> None:
        acc = _TraceAccumulator()
        huge_output = "x" * 20_000
        acc.accumulate(_make_tool_start_event("big_tool"))
        acc.accumulate(_make_tool_end_event("big_tool", huge_output))

        result = acc.finalize(model_name="test-model")
        result_step = next(s for s in result["steps"] if s["type"] == "tool_result")
        assert result_step["tool_output"].endswith("... [truncated]")
        assert len(result_step["tool_output"]) < 20_000


class TestTraceAccumulatorToolFailureDetection:
    """Tests for tool failure status detection."""

    def test_successful_tool_has_success_status(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_tool_start_event("calc"))
        acc.accumulate(_make_tool_end_event("calc", "42"))
        result = acc.finalize(model_name="test-model")
        result_step = next(s for s in result["steps"] if s["type"] == "tool_result")
        assert result_step["status"] == "success"

    def test_tool_with_error_in_data_is_failed(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_tool_start_event("broken"))
        event: dict[str, Any] = {
            "event": "on_tool_end",
            "name": "broken",
            "data": {"output": "error details", "error": "ConnectionRefused"},
        }
        acc.accumulate(event)
        result = acc.finalize(model_name="test-model")
        result_step = next(s for s in result["steps"] if s["type"] == "tool_result")
        assert result_step["status"] == "failed"

    def test_tool_with_error_status_attribute_is_failed(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_tool_start_event("flaky"))
        output = MagicMock()
        output.content = "something went wrong"
        output.status = "error"
        event: dict[str, Any] = {
            "event": "on_tool_end",
            "name": "flaky",
            "data": {"output": output},
        }
        acc.accumulate(event)
        result = acc.finalize(model_name="test-model")
        result_step = next(s for s in result["steps"] if s["type"] == "tool_result")
        assert result_step["status"] == "failed"

    def test_tool_with_dict_output_failed_status(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_tool_start_event("api_call"))
        event: dict[str, Any] = {
            "event": "on_tool_end",
            "name": "api_call",
            "data": {"output": {"status": "failed", "message": "404 not found"}},
        }
        acc.accumulate(event)
        result = acc.finalize(model_name="test-model")
        result_step = next(s for s in result["steps"] if s["type"] == "tool_result")
        assert result_step["status"] == "failed"


class TestTraceAccumulatorMixedSequences:
    """Tests for interleaved reasoning and tool events."""

    def test_reasoning_flushed_before_tool_call(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_chat_stream_event("Let me check"))
        acc.accumulate(_make_tool_start_event("search", {"q": "test"}))
        acc.accumulate(_make_tool_end_event("search", "found it"))
        acc.accumulate(_make_chat_stream_event("Based on results"))

        result = acc.finalize(model_name="test-model")
        types = [s["type"] for s in result["steps"]]
        assert types == ["reasoning", "tool_call", "tool_result", "reasoning"]

    def test_full_agent_trace_structure(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_chat_stream_event("Analyzing..."))
        acc.accumulate(_make_tool_start_event("splunk", {"query": "errors"}))
        acc.accumulate(_make_tool_end_event("splunk", "47 events"))
        acc.accumulate(_make_chat_stream_event("Found issues."))

        result = acc.finalize(model_name="claude-haiku", final_answer="Analysis complete.")

        assert result["model"] == "claude-haiku"
        assert isinstance(result["total_tokens"], int)
        assert isinstance(result["total_duration_ms"], int)
        types = [s["type"] for s in result["steps"]]
        assert types == ["reasoning", "tool_call", "tool_result", "reasoning", "final_answer"]
        assert result["steps"][-1]["content"] == "Analysis complete."

    def test_multiple_tool_calls_in_sequence(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_chat_stream_event("Checking"))
        acc.accumulate(_make_tool_start_event("tool_a", {}))
        acc.accumulate(_make_tool_end_event("tool_a", "result_a"))
        acc.accumulate(_make_tool_start_event("tool_b", {}))
        acc.accumulate(_make_tool_end_event("tool_b", "result_b"))

        result = acc.finalize(model_name="test-model")
        types = [s["type"] for s in result["steps"]]
        assert types == ["reasoning", "tool_call", "tool_result", "tool_call", "tool_result"]

    def test_tools_with_shared_name_prefix_match_correctly(self) -> None:
        """Regression: 'search' and 'search_web' must not cross-match."""
        acc = _TraceAccumulator()
        acc.accumulate(_make_tool_start_event("search", {"q": "a"}))
        acc.accumulate(_make_tool_start_event("search_web", {"q": "b"}))
        acc.accumulate(_make_tool_end_event("search_web", "web result"))
        acc.accumulate(_make_tool_end_event("search", "search result"))

        result = acc.finalize(model_name="test-model")
        tool_results = [s for s in result["steps"] if s["type"] == "tool_result"]
        assert tool_results[0]["tool_name"] == "search_web"
        assert tool_results[0]["tool_output"] == "web result"
        assert tool_results[1]["tool_name"] == "search"
        assert tool_results[1]["tool_output"] == "search result"

    def test_same_tool_called_twice_gets_correct_duration(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_tool_start_event("search", {"q": "first"}))
        acc.accumulate(_make_tool_end_event("search", "result 1"))
        acc.accumulate(_make_tool_start_event("search", {"q": "second"}))
        acc.accumulate(_make_tool_end_event("search", "result 2"))

        result = acc.finalize(model_name="test-model")
        tool_results = [s for s in result["steps"] if s["type"] == "tool_result"]
        assert len(tool_results) == 2
        assert all("duration_ms" in r for r in tool_results)


class TestTraceAccumulatorFinalize:
    """Tests for finalize behavior."""

    def test_finalize_with_final_answer(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_chat_stream_event("Done"))
        result = acc.finalize(model_name="test-model", final_answer="The answer is 42")

        final_steps = [s for s in result["steps"] if s["type"] == "final_answer"]
        assert len(final_steps) == 1
        assert final_steps[0]["content"] == "The answer is 42"

    def test_finalize_without_final_answer(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_chat_stream_event("Done"))
        result = acc.finalize(model_name="test-model")

        final_steps = [s for s in result["steps"] if s["type"] == "final_answer"]
        assert len(final_steps) == 0

    def test_finalize_empty_accumulator(self) -> None:
        acc = _TraceAccumulator()
        result = acc.finalize(model_name="test-model")

        assert result["model"] == "test-model"
        assert result["total_tokens"] == 0
        assert result["total_duration_ms"] == 0
        assert result["steps"] == []

    def test_all_steps_have_timestamp(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_chat_stream_event("Think"))
        acc.accumulate(_make_tool_start_event("tool", {}))
        acc.accumulate(_make_tool_end_event("tool", "out"))

        result = acc.finalize(model_name="test-model", final_answer="Done")
        for step in result["steps"]:
            assert "timestamp" in step
            assert isinstance(step["timestamp"], str)

    def test_total_tokens_sums_across_steps(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_chat_stream_event("Hello", output_tokens=10))
        acc.accumulate(_make_tool_start_event("tool", {}))
        acc.accumulate(_make_tool_end_event("tool", "out"))
        acc.accumulate(_make_chat_stream_event("World", output_tokens=5))

        result = acc.finalize(model_name="test-model")
        assert result["total_tokens"] == 15

    def test_total_tokens_do_not_double_count_with_final_usage_metadata(self) -> None:
        acc = _TraceAccumulator()
        # First chunk has no usage metadata; final chunk reports full output_tokens.
        acc.accumulate(_make_chat_stream_event("Hello"))
        acc.accumulate(_make_chat_stream_event(" world", output_tokens=12))

        result = acc.finalize(model_name="test-model")
        assert result["total_tokens"] == 12


class TestTraceAccumulatorUnknownEvents:
    """Tests for unrecognized event types."""

    def test_unknown_event_type_is_ignored(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate({"event": "on_chain_start", "data": {}})
        acc.accumulate({"event": "on_chain_end", "name": "LangGraph", "data": {}})
        result = acc.finalize(model_name="test-model")
        assert result["steps"] == []


class TestTraceAccumulatorParallelToolMatching:
    """Tests matching start/end for parallel calls with same tool name."""

    def test_parallel_same_tool_name_matches_by_run_id(self) -> None:
        acc = _TraceAccumulator()
        acc.accumulate(_make_tool_start_event("search", {"q": "first"}, run_id="run-1"))
        acc.accumulate(_make_tool_start_event("search", {"q": "second"}, run_id="run-2"))
        # Complete out of order
        acc.accumulate(_make_tool_end_event("search", "result-2", run_id="run-2"))
        acc.accumulate(_make_tool_end_event("search", "result-1", run_id="run-1"))

        result = acc.finalize(model_name="test-model")
        tool_results = [s for s in result["steps"] if s["type"] == "tool_result"]
        assert len(tool_results) == 2
        assert tool_results[0]["tool_output"] == "result-2"
        assert tool_results[1]["tool_output"] == "result-1"
        assert all("duration_ms" in r for r in tool_results)
