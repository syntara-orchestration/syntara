"""Unit tests for LLM metrics instrumentation."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import pytest
from prometheus_client import CollectorRegistry

from syntara.metrics.instrumentation import (
    LLMCallMetrics,
    LLMStreamTracker,
    _extract_token_usage,
    _record_llm_metrics,
    _resolve_model_provider,
    record_llm_call,
)
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


@dataclass
class _FakeUsageMetadata:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class _FakeAIMessage:
    content: str = "Hello"
    usage_metadata: _FakeUsageMetadata | None = None
    response_metadata: dict[str, Any] | None = None


def _make_response(
    *,
    input_tokens: int = 100,
    output_tokens: int = 50,
    model_name: str | None = None,
) -> _FakeAIMessage:
    """Build a fake LangChain AIMessage with token metadata."""
    resp_meta: dict[str, Any] = {}
    if model_name:
        resp_meta["model_name"] = model_name
    return _FakeAIMessage(
        content="Hello from LLM",
        usage_metadata=_FakeUsageMetadata(input_tokens=input_tokens, output_tokens=output_tokens),
        response_metadata=resp_meta,
    )


def _make_response_legacy_tokens(
    *,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
) -> _FakeAIMessage:
    """Build a response with old-style token_usage dict."""
    return _FakeAIMessage(
        content="Legacy response",
        usage_metadata=None,
        response_metadata={
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
        },
    )


async def _async_response(**kwargs: Any) -> _FakeAIMessage:  # noqa: ANN401
    """Return a fake AIMessage as an awaitable."""
    await asyncio.sleep(0)
    return _make_response(**kwargs)


async def _async_raise(exc: BaseException) -> Any:  # noqa: ANN401
    """Raise an exception as an awaitable."""
    await asyncio.sleep(0)
    raise exc


# =============================================================================
# _extract_token_usage
# =============================================================================


class TestExtractTokenUsage:
    """Tests for the _extract_token_usage helper."""

    def test_extracts_from_usage_metadata(self) -> None:
        """Token counts are extracted from the newer usage_metadata attribute."""
        resp = _make_response(input_tokens=200, output_tokens=80)
        inp, out = _extract_token_usage(resp)
        assert inp == 200
        assert out == 80

    def test_extracts_from_legacy_token_usage(self) -> None:
        """Token counts are extracted from the older response_metadata.token_usage dict."""
        resp = _make_response_legacy_tokens(prompt_tokens=300, completion_tokens=120)
        inp, out = _extract_token_usage(resp)
        assert inp == 300
        assert out == 120

    def test_extracts_from_usage_metadata_dict(self) -> None:
        """Token counts are extracted when usage_metadata is a TypedDict (real LangChain)."""
        resp = _FakeAIMessage(
            content="Hello",
            usage_metadata={"input_tokens": 350, "output_tokens": 120, "total_tokens": 470},  # type: ignore[arg-type]
        )
        inp, out = _extract_token_usage(resp)
        assert inp == 350
        assert out == 120

    def test_returns_zero_when_no_metadata(self) -> None:
        """Returns (0, 0) when neither metadata source is present."""
        inp, out = _extract_token_usage(_FakeAIMessage(content="plain"))
        assert (inp, out) == (0, 0)


# =============================================================================
# _resolve_model_provider
# =============================================================================


class TestResolveModelProvider:
    """Tests for the _resolve_model_provider helper."""

    def test_explicit_model_and_provider(self) -> None:
        """Explicit args are used as-is."""
        m, p = _resolve_model_provider(model="gpt-4", provider="openai")
        assert m == "gpt-4"
        assert p == "openai"

    def test_infers_provider_from_slash(self) -> None:
        """Provider is inferred from 'vendor/model' pattern."""
        _, p = _resolve_model_provider(model="anthropic/claude-3.5-sonnet")
        assert p == "anthropic"

    def test_defaults_to_unknown(self) -> None:
        """Returns 'unknown' when nothing is provided."""
        assert _resolve_model_provider() == ("unknown", "unknown")

    def test_extracts_from_llm_instance(self) -> None:
        """Model name is read from llm.model_name when model arg is None."""

        class FakeLLM:
            model_name = "openai/gpt-4o"

        m, p = _resolve_model_provider(llm=FakeLLM())
        assert m == "openai/gpt-4o"
        assert p == "openai"


# =============================================================================
# _record_llm_metrics
# =============================================================================


class TestRecordLLMMetrics:
    """Tests for the _record_llm_metrics flush helper."""

    def test_records_duration_with_labels(self, recorder: MetricsRecorder) -> None:
        """LLM_DURATION is recorded with model/provider labels."""
        _record_llm_metrics(recorder, LLMCallMetrics(duration_ms=250.0, model="gpt-4", provider="openai"))

        results = list(recorder.query(metric_types={MetricType.LLM_DURATION}))
        assert len(results) == 1
        assert results[0].value == pytest.approx(250.0)
        assert results[0].labels["model"] == "gpt-4"

    def test_records_tokens_when_nonzero(self, recorder: MetricsRecorder) -> None:
        """Non-zero token counts are recorded; zero counts are skipped."""
        _record_llm_metrics(recorder, LLMCallMetrics(input_tokens=100, output_tokens=50, model="m"))

        assert len(list(recorder.query(metric_types={MetricType.LLM_TOKENS_INPUT}))) == 1
        assert len(list(recorder.query(metric_types={MetricType.LLM_TOKENS_OUTPUT}))) == 1

    def test_skips_zero_tokens(self, recorder: MetricsRecorder) -> None:
        """Zero token counts produce no metric records."""
        _record_llm_metrics(recorder, LLMCallMetrics(input_tokens=0, output_tokens=0, model="m"))

        assert len(list(recorder.query(metric_types={MetricType.LLM_TOKENS_INPUT}))) == 0
        assert len(list(recorder.query(metric_types={MetricType.LLM_TOKENS_OUTPUT}))) == 0

    def test_status_records_event_with_label(self, recorder: MetricsRecorder) -> None:
        """LLM_STATUS always records value=1.0 with status conveyed via label."""
        _record_llm_metrics(recorder, LLMCallMetrics(status="success", model="m"))
        _record_llm_metrics(recorder, LLMCallMetrics(status="error", model="m"))

        results = list(recorder.query(metric_types={MetricType.LLM_STATUS}))
        assert all(r.value == pytest.approx(1.0) for r in results)
        statuses = sorted(r.labels["status"] for r in results)
        assert statuses == ["error", "success"]

    def test_increments_llm_calls_counter(self, recorder: MetricsRecorder) -> None:
        """Each flush increments the llm_calls summary counter."""
        _record_llm_metrics(recorder, LLMCallMetrics(model="m"))
        _record_llm_metrics(recorder, LLMCallMetrics(model="m"))

        assert recorder.get_summary().llm_calls == 2


# =============================================================================
# record_llm_call
# =============================================================================


class TestRecordLLMCall:
    """Tests for the record_llm_call async wrapper."""

    @pytest.mark.asyncio
    async def test_records_duration_and_labels(self, recorder: MetricsRecorder) -> None:
        """Duration, model, provider, and status labels are recorded on success."""
        await record_llm_call(
            recorder,
            lambda: _async_response(input_tokens=150, output_tokens=60),
            model="gpt-4",
            provider="openai",
        )

        durations = list(recorder.query(metric_types={MetricType.LLM_DURATION}))
        assert len(durations) == 1
        assert durations[0].value > 0
        assert durations[0].labels["status"] == "success"

    @pytest.mark.asyncio
    async def test_preserves_return_value(self, recorder: MetricsRecorder) -> None:
        """The original return value passes through unchanged."""
        result = await record_llm_call(recorder, _async_response, model="m")
        assert isinstance(result, _FakeAIMessage)
        assert result.content == "Hello from LLM"

    @pytest.mark.asyncio
    async def test_records_error_and_reraises(self, recorder: MetricsRecorder) -> None:
        """On failure: error status is recorded and the exception propagates."""
        msg = "API error"
        with pytest.raises(RuntimeError, match=msg):
            await record_llm_call(recorder, lambda: _async_raise(RuntimeError(msg)), model="m")

        statuses = list(recorder.query(metric_types={MetricType.LLM_STATUS}))
        assert statuses[0].labels["status"] == "error"

    @pytest.mark.asyncio
    async def test_duration_recorded_on_error(self, recorder: MetricsRecorder) -> None:
        """Duration is still captured even when the call raises."""
        with pytest.raises(TimeoutError):
            await record_llm_call(recorder, lambda: _async_raise(TimeoutError("t")), model="m")

        durations = list(recorder.query(metric_types={MetricType.LLM_DURATION}))
        assert len(durations) == 1
        assert durations[0].value > 0

    @pytest.mark.asyncio
    async def test_extracts_model_from_response_metadata(self, recorder: MetricsRecorder) -> None:
        """When model is not specified, it is auto-detected from response metadata."""
        await record_llm_call(
            recorder,
            lambda: _async_response(model_name="anthropic/claude-3.5-sonnet"),
        )

        durations = list(recorder.query(metric_types={MetricType.LLM_DURATION}))
        assert durations[0].labels["model"] == "anthropic/claude-3.5-sonnet"
        assert durations[0].labels["provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_active_llm_requests_gauge_lifecycle(self, recorder: MetricsRecorder) -> None:
        """Gauge is 0 before, incremented during, and 0 again after a successful call."""
        assert recorder.prometheus.active_llm_requests._value.get() == pytest.approx(0.0)

        await record_llm_call(recorder, _async_response, model="m")

        assert recorder.prometheus.active_llm_requests._value.get() == pytest.approx(0.0)
        assert recorder.get_summary().active_llm_requests == 0

    @pytest.mark.asyncio
    async def test_active_llm_requests_gauge_decrements_on_error(self, recorder: MetricsRecorder) -> None:
        """Gauge returns to 0 even when the LLM call raises."""
        with pytest.raises(RuntimeError):
            await record_llm_call(recorder, lambda: _async_raise(RuntimeError("fail")), model="m")

        assert recorder.prometheus.active_llm_requests._value.get() == pytest.approx(0.0)
        assert recorder.get_summary().active_llm_requests == 0


# =============================================================================
# Prometheus dispatch
# =============================================================================


class TestPrometheusDispatch:
    """Verify Prometheus instruments are updated for LLM metric types."""

    def test_token_counters_increment(self, recorder: MetricsRecorder) -> None:
        """LLM_TOKENS_INPUT and LLM_TOKENS_OUTPUT increment their Prometheus counters."""
        recorder.record(MetricType.LLM_TOKENS_INPUT, 200.0, unit="tokens", labels={"model": "gpt-4"})
        recorder.record(MetricType.LLM_TOKENS_OUTPUT, 80.0, unit="tokens", labels={"model": "gpt-4"})

        assert recorder.prometheus.llm_tokens_input_total.labels(model="gpt-4")._value.get() == pytest.approx(200.0)
        assert recorder.prometheus.llm_tokens_output_total.labels(model="gpt-4")._value.get() == pytest.approx(80.0)

    def test_status_increments_llm_calls_total(self, recorder: MetricsRecorder) -> None:
        """LLM_STATUS is the sole owner of llm_calls_total in Prometheus."""
        recorder.record(MetricType.LLM_STATUS, 1.0, labels={"model": "gpt-4", "status": "success"})

        value = recorder.prometheus.llm_calls_total.labels(model="gpt-4", status="success")._value.get()
        assert value == pytest.approx(1.0)

    def test_ttft_updates_histogram(self, recorder: MetricsRecorder) -> None:
        """LLM_TTFT populates the Prometheus TTFT histogram."""
        recorder.record(MetricType.LLM_TTFT, 120.0, unit="ms", labels={"model": "gpt-4"})

        assert recorder.prometheus.ttft_seconds.labels(model="gpt-4")._sum.get() == pytest.approx(0.12)


# =============================================================================
# LLMStreamTracker
# =============================================================================


class TestLLMStreamTracker:
    """Tests for TTFT tracking via LangGraph astream_events."""

    def test_records_ttft_on_first_stream_chunk(self, recorder: MetricsRecorder) -> None:
        """TTFT is measured from on_chat_model_start to the first on_chat_model_stream."""
        tracker = LLMStreamTracker(recorder=recorder, model="gpt-4")

        tracker.process_event({"event": "on_chat_model_start", "run_id": "run-1"})
        time.sleep(0.01)
        tracker.process_event({"event": "on_chat_model_stream", "run_id": "run-1", "data": {}})

        results = list(recorder.query(metric_types={MetricType.LLM_TTFT}))
        assert len(results) == 1
        assert results[0].value >= 5
        assert results[0].labels["model"] == "gpt-4"

    def test_only_first_chunk_records_ttft(self, recorder: MetricsRecorder) -> None:
        """Subsequent stream chunks for the same LLM call do not produce additional TTFT records."""
        tracker = LLMStreamTracker(recorder=recorder, model="m")

        tracker.process_event({"event": "on_chat_model_start", "run_id": "run-1"})
        tracker.process_event({"event": "on_chat_model_stream", "run_id": "run-1", "data": {}})
        tracker.process_event({"event": "on_chat_model_stream", "run_id": "run-1", "data": {}})

        assert len(list(recorder.query(metric_types={MetricType.LLM_TTFT}))) == 1

    def test_tracks_multiple_llm_calls_independently(self, recorder: MetricsRecorder) -> None:
        """Each LLM call (distinct run_id) gets its own TTFT measurement."""
        tracker = LLMStreamTracker(recorder=recorder, model="m")

        tracker.process_event({"event": "on_chat_model_start", "run_id": "run-1"})
        tracker.process_event({"event": "on_chat_model_stream", "run_id": "run-1", "data": {}})
        tracker.process_event({"event": "on_chat_model_start", "run_id": "run-2"})
        tracker.process_event({"event": "on_chat_model_stream", "run_id": "run-2", "data": {}})

        assert len(list(recorder.query(metric_types={MetricType.LLM_TTFT}))) == 2

    def test_ignores_stream_without_preceding_start(self, recorder: MetricsRecorder) -> None:
        """An orphan on_chat_model_stream (no matching start) is silently ignored."""
        tracker = LLMStreamTracker(recorder=recorder, model="m")

        tracker.process_event({"event": "on_chat_model_stream", "run_id": "orphan", "data": {}})

        assert len(list(recorder.query(metric_types={MetricType.LLM_TTFT}))) == 0
