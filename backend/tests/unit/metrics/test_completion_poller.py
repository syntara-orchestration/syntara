"""Unit tests for completion_poller helper functions.

These pure-logic helpers were extracted from _emit_invocation_agent_metrics
to reduce cognitive complexity.  They require no database — only a
MetricsRecorder and lightweight model instances.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from prometheus_client import CollectorRegistry

from syntara.agent_orchestrator.models.invocation import InvocationStatus
from syntara.metrics.completion_poller import _emit_agent_duration, _emit_llm_metrics, _emit_routing_duration
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import MetricType


@pytest.fixture
def recorder() -> MetricsRecorder:
    """Fresh MetricsRecorder with an isolated Prometheus registry."""
    return MetricsRecorder(
        retention_seconds=3600,
        max_records=10_000,
        prometheus_registry=CollectorRegistry(),
    )


def _make_invocation(
    *,
    status: InvocationStatus = InvocationStatus.COMPLETED,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> MagicMock:
    now = datetime.now(UTC)
    inv = MagicMock()
    inv.id = uuid4()
    inv.status = status
    inv.started_at = started_at if started_at is not None else now - timedelta(seconds=2)
    inv.completed_at = completed_at if completed_at is not None else now
    return inv


# ---------------------------------------------------------------------------
# _emit_routing_duration
# ---------------------------------------------------------------------------


class TestEmitRoutingDuration:
    """Tests for _emit_routing_duration helper."""

    def test_emits_routing_duration(self, recorder: MetricsRecorder) -> None:
        inv_id = str(uuid4())
        meta = {"routing_duration_ms": 42.5, "routed_to_agent": "agent-alpha"}

        result = _emit_routing_duration(inv_id, meta, recorder)

        assert result is True
        records = list(recorder.query(metric_types={MetricType.AGENT_ROUTING_DURATION}))
        assert len(records) == 1
        assert records[0].value == pytest.approx(42.5)
        assert records[0].labels["invocation_id"] == inv_id
        assert records[0].labels["target_agent"] == "agent-alpha"

    def test_emits_routing_duration_int(self, recorder: MetricsRecorder) -> None:
        inv_id = str(uuid4())
        meta = {"routing_duration_ms": 100}

        result = _emit_routing_duration(inv_id, meta, recorder)

        assert result is True
        records = list(recorder.query(metric_types={MetricType.AGENT_ROUTING_DURATION}))
        assert records[0].value == pytest.approx(100.0)

    def test_defaults_target_agent_to_unknown(self, recorder: MetricsRecorder) -> None:
        inv_id = str(uuid4())
        meta = {"routing_duration_ms": 10.0}

        _emit_routing_duration(inv_id, meta, recorder)

        records = list(recorder.query(metric_types={MetricType.AGENT_ROUTING_DURATION}))
        assert records[0].labels["target_agent"] == "unknown"

    def test_returns_false_when_meta_is_none(self, recorder: MetricsRecorder) -> None:
        assert _emit_routing_duration(str(uuid4()), {}, recorder) is False
        assert len(list(recorder.query(metric_types={MetricType.AGENT_ROUTING_DURATION}))) == 0

    def test_returns_false_when_routing_ms_missing(self, recorder: MetricsRecorder) -> None:
        assert _emit_routing_duration(str(uuid4()), {"other": "data"}, recorder) is False

    def test_returns_false_when_routing_ms_is_string(self, recorder: MetricsRecorder) -> None:
        meta = {"routing_duration_ms": "not-a-number"}
        assert _emit_routing_duration(str(uuid4()), meta, recorder) is False

    def test_returns_false_when_meta_is_not_dict(self, recorder: MetricsRecorder) -> None:
        assert _emit_routing_duration(str(uuid4()), "bad", recorder) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _emit_agent_duration
# ---------------------------------------------------------------------------


class TestEmitAgentDuration:
    """Tests for _emit_agent_duration helper."""

    def test_emits_duration_and_status_for_completed(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.COMPLETED)

        result = _emit_agent_duration(inv, recorder)

        assert result is True
        durations = list(recorder.query(metric_types={MetricType.AGENT_INVOCATION_DURATION}))
        assert len(durations) == 1
        assert durations[0].value > 0
        assert durations[0].labels["status"] == "success"

        statuses = list(recorder.query(metric_types={MetricType.AGENT_STATUS}))
        assert len(statuses) == 1
        assert statuses[0].labels["status"] == "success"

    def test_emits_failed_status(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.FAILED)

        _emit_agent_duration(inv, recorder)

        durations = list(recorder.query(metric_types={MetricType.AGENT_INVOCATION_DURATION}))
        assert durations[0].labels["status"] == "failed"

    def test_emits_cancelled_with_only_completed_at(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.CANCELLED)
        inv.started_at = None

        result = _emit_agent_duration(inv, recorder)

        assert result is True
        assert len(list(recorder.query(metric_types={MetricType.AGENT_INVOCATION_DURATION}))) == 0
        statuses = list(recorder.query(metric_types={MetricType.AGENT_STATUS}))
        assert len(statuses) == 1
        assert statuses[0].labels["status"] == "cancelled"

    def test_emits_cancelled_with_both_timestamps(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.CANCELLED)

        result = _emit_agent_duration(inv, recorder)

        assert result is True
        durations = list(recorder.query(metric_types={MetricType.AGENT_INVOCATION_DURATION}))
        assert len(durations) == 1
        assert durations[0].labels["status"] == "cancelled"

    def test_returns_false_when_no_timestamps(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.COMPLETED)
        inv.started_at = None
        inv.completed_at = None

        result = _emit_agent_duration(inv, recorder)

        assert result is False
        assert len(list(recorder.query(metric_types={MetricType.AGENT_INVOCATION_DURATION}))) == 0
        assert len(list(recorder.query(metric_types={MetricType.AGENT_STATUS}))) == 0

    def test_returns_false_when_only_started_at(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.RUNNING)
        inv.completed_at = None

        result = _emit_agent_duration(inv, recorder)

        assert result is False


# ---------------------------------------------------------------------------
# _emit_llm_metrics
# ---------------------------------------------------------------------------


def _make_token_record(
    *,
    prompt_tokens: int | None = 100,
    completion_tokens: int | None = 50,
) -> MagicMock:
    rec = MagicMock()
    rec.prompt_tokens = prompt_tokens
    rec.completion_tokens = completion_tokens
    return rec


class TestEmitLlmMetrics:
    """Tests for _emit_llm_metrics helper."""

    def test_emits_input_and_output_tokens(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.COMPLETED)
        inv.model_name = "openai/gpt-4"
        token_rec = _make_token_record(prompt_tokens=200, completion_tokens=80)

        result = _emit_llm_metrics(inv, token_rec, recorder)

        assert result is True
        inputs = list(recorder.query(metric_types={MetricType.LLM_TOKENS_INPUT}))
        assert len(inputs) == 1
        assert inputs[0].value == pytest.approx(200.0)
        assert inputs[0].labels["model"] == "openai/gpt-4"
        assert inputs[0].labels["provider"] == "openai"
        assert inputs[0].labels["status"] == "success"

        outputs = list(recorder.query(metric_types={MetricType.LLM_TOKENS_OUTPUT}))
        assert len(outputs) == 1
        assert outputs[0].value == pytest.approx(80.0)

    def test_emits_duration_when_timestamps_present(self, recorder: MetricsRecorder) -> None:
        now = datetime.now(UTC)
        inv = _make_invocation(
            status=InvocationStatus.COMPLETED,
            started_at=now - timedelta(seconds=3),
            completed_at=now,
        )
        inv.model_name = "anthropic/claude-3"
        token_rec = _make_token_record()

        _emit_llm_metrics(inv, token_rec, recorder)

        durations = list(recorder.query(metric_types={MetricType.LLM_DURATION}))
        assert len(durations) == 1
        assert durations[0].value == pytest.approx(3000.0)

    def test_skips_duration_without_started_at(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.COMPLETED)
        inv.started_at = None
        inv.model_name = "openai/gpt-4"
        token_rec = _make_token_record()

        _emit_llm_metrics(inv, token_rec, recorder)

        assert len(list(recorder.query(metric_types={MetricType.LLM_DURATION}))) == 0

    def test_emits_status_metric(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.COMPLETED)
        inv.model_name = "openai/gpt-4"
        token_rec = _make_token_record()

        _emit_llm_metrics(inv, token_rec, recorder)

        statuses = list(recorder.query(metric_types={MetricType.LLM_STATUS}))
        assert len(statuses) == 1
        assert statuses[0].value == pytest.approx(1.0)

    def test_returns_false_when_both_tokens_zero(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.COMPLETED)
        inv.model_name = "openai/gpt-4"
        token_rec = _make_token_record(prompt_tokens=0, completion_tokens=0)

        result = _emit_llm_metrics(inv, token_rec, recorder)

        assert result is False
        assert len(list(recorder.query(metric_types={MetricType.LLM_TOKENS_INPUT}))) == 0
        assert len(list(recorder.query(metric_types={MetricType.LLM_TOKENS_OUTPUT}))) == 0
        assert len(list(recorder.query(metric_types={MetricType.LLM_STATUS}))) == 0

    def test_returns_false_when_both_tokens_none(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.COMPLETED)
        inv.model_name = "openai/gpt-4"
        token_rec = _make_token_record(prompt_tokens=None, completion_tokens=None)

        result = _emit_llm_metrics(inv, token_rec, recorder)

        assert result is False

    def test_emits_only_input_when_completion_zero(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.COMPLETED)
        inv.model_name = "openai/gpt-4"
        token_rec = _make_token_record(prompt_tokens=150, completion_tokens=0)

        result = _emit_llm_metrics(inv, token_rec, recorder)

        assert result is True
        assert len(list(recorder.query(metric_types={MetricType.LLM_TOKENS_INPUT}))) == 1
        assert len(list(recorder.query(metric_types={MetricType.LLM_TOKENS_OUTPUT}))) == 0

    def test_emits_only_output_when_prompt_zero(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.COMPLETED)
        inv.model_name = "openai/gpt-4"
        token_rec = _make_token_record(prompt_tokens=0, completion_tokens=75)

        result = _emit_llm_metrics(inv, token_rec, recorder)

        assert result is True
        assert len(list(recorder.query(metric_types={MetricType.LLM_TOKENS_INPUT}))) == 0
        assert len(list(recorder.query(metric_types={MetricType.LLM_TOKENS_OUTPUT}))) == 1

    def test_provider_unknown_when_no_slash_in_model(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.COMPLETED)
        inv.model_name = "gpt-4"
        token_rec = _make_token_record()

        _emit_llm_metrics(inv, token_rec, recorder)

        inputs = list(recorder.query(metric_types={MetricType.LLM_TOKENS_INPUT}))
        assert inputs[0].labels["provider"] == "unknown"
        assert inputs[0].labels["model"] == "gpt-4"

    def test_model_defaults_to_unknown_when_none(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.COMPLETED)
        inv.model_name = None
        token_rec = _make_token_record()

        _emit_llm_metrics(inv, token_rec, recorder)

        inputs = list(recorder.query(metric_types={MetricType.LLM_TOKENS_INPUT}))
        assert inputs[0].labels["model"] == "unknown"
        assert inputs[0].labels["provider"] == "unknown"

    def test_failed_invocation_status_label(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.FAILED)
        inv.model_name = "openai/gpt-4"
        token_rec = _make_token_record()

        _emit_llm_metrics(inv, token_rec, recorder)

        inputs = list(recorder.query(metric_types={MetricType.LLM_TOKENS_INPUT}))
        assert inputs[0].labels["status"] == "failed"

    def test_increments_llm_calls_counter(self, recorder: MetricsRecorder) -> None:
        inv = _make_invocation(status=InvocationStatus.COMPLETED)
        inv.model_name = "openai/gpt-4"
        token_rec = _make_token_record()

        _emit_llm_metrics(inv, token_rec, recorder)

        assert recorder._counters["llm_calls"] == 1
