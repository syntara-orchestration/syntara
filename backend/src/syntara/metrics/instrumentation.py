"""LLM metrics instrumentation for the Syntara metrics subsystem.

Provides a wrapper function to instrument LLM calls with metrics
recording.  All instrumentation is transparent: it does **not** alter
the return value, exception behaviour, or side-effects of the wrapped
LLM call.

Recorded metrics:

* ``LLM_DURATION`` - wall-clock duration of the LLM request (ms).
* ``LLM_TOKENS_INPUT`` / ``LLM_TOKENS_OUTPUT`` - token counts extracted
  from the LangChain response metadata.
* ``LLM_TTFT`` - Time To First Token, measured via LangGraph streaming
  events (ms).
* ``LLM_STATUS`` - event count (always 1.0) with outcome in ``status`` label.

Every metric carries ``model`` and ``provider`` labels plus a ``status``
label (``"success"`` or ``"error"``).

Usage examples::

    # --- Wrapper for async invoke-style calls ---
    result = await record_llm_call(
        recorder,
        lambda: llm.ainvoke(messages),
        model="anthropic/claude-3.5-sonnet",
    )

    # --- TTFT tracking via LangGraph astream_events ---
    tracker = LLMStreamTracker(recorder, model="gpt-4")
    async for event in graph.astream_events(...):
        tracker.process_event(event)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from syntara.metrics.types import MetricType

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from syntara.metrics.recorder import MetricsRecorder

logger = structlog.stdlib.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class LLMCallMetrics:
    """Captured metrics from a single LLM call."""

    duration_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "unknown"
    provider: str = "unknown"
    status: str = "success"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_token_usage(response: Any) -> tuple[int, int]:  # noqa: ANN401
    """Extract input/output token counts from a LangChain response.

    Supports both the newer ``usage_metadata`` attribute (a TypedDict
    with ``input_tokens``/``output_tokens`` keys) and the older
    ``response_metadata["token_usage"]`` dictionary.
    """
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        usage = response.usage_metadata
        if isinstance(usage, dict):
            return (
                usage.get("input_tokens", 0) or 0,
                usage.get("output_tokens", 0) or 0,
            )
        return (
            getattr(usage, "input_tokens", 0) or 0,
            getattr(usage, "output_tokens", 0) or 0,
        )

    if hasattr(response, "response_metadata") and isinstance(response.response_metadata, dict):
        token_usage = response.response_metadata.get("token_usage", {})
        if token_usage:
            return (
                token_usage.get("prompt_tokens", 0) or 0,
                token_usage.get("completion_tokens", 0) or 0,
            )

    return 0, 0


def _resolve_model_provider(
    model: str | None = None,
    provider: str | None = None,
    *,
    llm: Any = None,  # noqa: ANN401
) -> tuple[str, str]:
    """Resolve model name and provider from explicit args or an LLM instance."""
    resolved_model = model or "unknown"
    resolved_provider = provider or "unknown"

    if llm is not None and resolved_model == "unknown" and hasattr(llm, "model_name"):
        resolved_model = str(llm.model_name)

    if resolved_provider == "unknown" and "/" in resolved_model:
        resolved_provider = resolved_model.split("/", 1)[0]

    return resolved_model, resolved_provider


def _record_llm_metrics(
    recorder: MetricsRecorder,
    metrics: LLMCallMetrics,
) -> None:
    """Flush all captured LLM metrics to *recorder*."""
    labels = {
        "model": metrics.model,
        "provider": metrics.provider,
        "status": metrics.status,
    }

    recorder.record(MetricType.LLM_DURATION, metrics.duration_ms, unit="ms", labels=labels)

    if metrics.input_tokens > 0:
        recorder.record(
            MetricType.LLM_TOKENS_INPUT,
            float(metrics.input_tokens),
            unit="tokens",
            labels=labels,
        )

    if metrics.output_tokens > 0:
        recorder.record(
            MetricType.LLM_TOKENS_OUTPUT,
            float(metrics.output_tokens),
            unit="tokens",
            labels=labels,
        )

    recorder.record(
        MetricType.LLM_STATUS,
        1.0,
        labels=labels,
    )

    recorder.increment("llm_calls")


# ---------------------------------------------------------------------------
# Async wrapper for invoke-style calls
# ---------------------------------------------------------------------------


async def record_llm_call[T](
    recorder: MetricsRecorder,
    call: Callable[[], Awaitable[T]],
    *,
    model: str | None = None,
    provider: str | None = None,
) -> T:
    """Record metrics around an async LLM call.

    Wraps *call* (a zero-argument async callable) and records duration,
    token counts, model/provider labels, and success/failure status
    without altering the return value or exception behaviour.

    Args:
        recorder: Target :class:`MetricsRecorder`.
        call: Zero-argument async callable that performs the LLM request
            (e.g. ``lambda: llm.ainvoke(messages)``).
        model: Model name.  When *None*, extracted from response metadata.
        provider: Provider name.  When *None* and model contains ``/``,
            the prefix is used (e.g. ``"anthropic"``).

    Returns:
        The value returned by *call*.

    """
    resolved_model, resolved_provider = _resolve_model_provider(
        model=model,
        provider=provider,
    )

    start = time.perf_counter()
    status = "success"
    result: Any = None

    recorder.increment_gauge("active_llm_requests")
    try:
        result = await call()
    except Exception:
        status = "error"
        raise
    finally:
        recorder.decrement_gauge("active_llm_requests")
        duration_ms = (time.perf_counter() - start) * 1000

        input_tokens, output_tokens = 0, 0
        resp_model = resolved_model
        resp_provider = resolved_provider

        if result is not None:
            input_tokens, output_tokens = _extract_token_usage(result)
            if model is None and hasattr(result, "response_metadata"):
                meta_model = result.response_metadata.get("model_name")
                if meta_model:
                    resp_model, resp_provider = _resolve_model_provider(
                        model=meta_model,
                        provider=provider,
                    )

        collected = LLMCallMetrics(
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=resp_model,
            provider=resp_provider,
            status=status,
        )

        try:
            _record_llm_metrics(recorder, collected)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to record LLM metrics", exc_info=True)

    return result  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# LangGraph streaming TTFT tracker
# ---------------------------------------------------------------------------


@dataclass
class LLMStreamTracker:
    """Track Time To First Token from LangGraph ``astream_events``.

    Feed every event dict from ``graph.astream_events()`` into
    :meth:`process_event`.  The tracker records start times on
    ``on_chat_model_start`` events and calculates TTFT when the first
    ``on_chat_model_stream`` event arrives for the same ``run_id``.

    TTFT values are flushed to the recorder immediately upon capture.

    Args:
        recorder: Target :class:`MetricsRecorder`.
        model: Default model name label.

    """

    recorder: MetricsRecorder
    model: str = "unknown"
    _call_starts: dict[str, float] = field(default_factory=dict, repr=False)

    def process_event(self, event: dict[str, Any]) -> None:
        """Process a single LangGraph streaming event.

        Call this for every event yielded by ``graph.astream_events()``.
        Only ``on_chat_model_start`` and ``on_chat_model_stream`` events
        are relevant; all others are ignored.
        """
        event_type = event.get("event")
        run_id = event.get("run_id", "")

        if event_type == "on_chat_model_start":
            self._call_starts[run_id] = time.perf_counter()

        elif event_type == "on_chat_model_stream" and run_id in self._call_starts:
            start = self._call_starts.pop(run_id)
            ttft_ms = (time.perf_counter() - start) * 1000
            try:
                self.recorder.record(
                    MetricType.LLM_TTFT,
                    ttft_ms,
                    unit="ms",
                    labels={"model": self.model},
                )
            except Exception:  # noqa: BLE001
                logger.debug("Failed to record TTFT metric", exc_info=True)
