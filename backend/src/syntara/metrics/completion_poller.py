"""Background poller that emits workflow/activity completion metrics.

Periodically queries the database for recently completed executions and
emits their metrics into the API server's MetricsRecorder and Prometheus
registry.  This removes the dependency on a user hitting the GET endpoint
for metrics to appear.

Uses the shared ``PeriodicWorker`` with ``coordinate=True`` so that only
one API-server instance across a scaled deployment emits metrics per cycle
(via PostgreSQL advisory locks).

The poller reuses the same deduplication set as the on-read path, so
executions are never double-counted regardless of which path fires first.

Agent metrics (AGENT_ROUTING_DURATION, AGENT_INVOCATION_DURATION,
AGENT_STATUS) and LLM metrics (LLM_DURATION, LLM_TOKENS_INPUT,
LLM_TOKENS_OUTPUT, LLM_STATUS) are recorded by the Temporal worker
process which has a separate in-memory MetricsRecorder.  This poller
bridges them into the API server's store by reading persisted timing
data from completed invocations and token usage records.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import structlog
from sqlalchemy.orm import selectinload
from sqlmodel import select

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.agent_orchestrator.token_manager.models import TokenUsageRecord
from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.workers.periodic import PeriodicWorker
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.emission import emit_completion_metrics, emitted_invocations
from syntara.metrics.types import MetricType
from syntara.workflows.models.execution import TERMINAL_EXECUTION_STATUSES, Execution

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.metrics.recorder import MetricsRecorder

logger = structlog.stdlib.get_logger(__name__)

TERMINAL_INVOCATION_STATUSES = frozenset(
    {
        InvocationStatus.COMPLETED,
        InvocationStatus.FAILED,
        InvocationStatus.CANCELLED,
    }
)


def _emit_routing_duration(
    inv_id: str,
    meta: dict[str, Any],
    recorder: MetricsRecorder,
) -> bool:
    """Emit AGENT_ROUTING_DURATION from persisted orchestrator timing."""
    routing_ms = meta.get("routing_duration_ms") if isinstance(meta, dict) else None
    if not isinstance(routing_ms, (int, float)):
        return False
    recorder.record(
        MetricType.AGENT_ROUTING_DURATION,
        float(routing_ms),
        unit="ms",
        labels={
            "invocation_id": inv_id,
            "target_agent": str(meta.get("routed_to_agent", "unknown")),
        },
    )
    return True


def _emit_agent_duration(
    invocation: Invocation,
    recorder: MetricsRecorder,
) -> bool:
    """Emit AGENT_INVOCATION_DURATION and AGENT_STATUS from DB timestamps."""
    if invocation.started_at and invocation.completed_at:
        duration_ms = (invocation.completed_at - invocation.started_at).total_seconds() * 1000
        status = "success" if invocation.status == InvocationStatus.COMPLETED else invocation.status.value
        recorder.record(
            MetricType.AGENT_INVOCATION_DURATION,
            duration_ms,
            unit="ms",
            labels={"invocation_id": str(invocation.id), "status": status},
        )
        recorder.record(
            MetricType.AGENT_STATUS,
            value=1,
            labels={"invocation_id": str(invocation.id), "status": status},
        )
        return True
    if invocation.status == InvocationStatus.CANCELLED and invocation.completed_at:
        recorder.record(
            MetricType.AGENT_STATUS,
            value=1,
            labels={"invocation_id": str(invocation.id), "status": "cancelled"},
        )
        return True
    return False


def _emit_invocation_agent_metrics(
    invocation: Invocation,
    recorder: MetricsRecorder,
    token_record: TokenUsageRecord | None = None,
) -> bool:
    """Emit agent and LLM metrics for a completed invocation.

    Reads ``routing_duration_ms`` and invocation timing from the
    persisted result metadata and records AGENT_ROUTING_DURATION,
    AGENT_INVOCATION_DURATION, and AGENT_STATUS.

    When a *token_record* is provided, also bridges LLM metrics
    (LLM_TOKENS_INPUT, LLM_TOKENS_OUTPUT, LLM_DURATION, LLM_STATUS)
    from the persisted ``TokenUsageRecord`` into the API server's
    in-memory store.  The Temporal worker records these metrics in its
    own process memory; this poller makes them visible to the internal
    metrics API.

    Returns True if metrics were emitted, False if skipped.
    """
    if invocation.id in emitted_invocations:
        return False
    if invocation.status not in TERMINAL_INVOCATION_STATUSES:
        return False

    inv_id = str(invocation.id)
    result = invocation.result or {}
    meta = cast("dict[str, Any]", result.get("response_metadata", {}))

    emitted_any = _emit_routing_duration(inv_id, meta, recorder)
    emitted_any = _emit_agent_duration(invocation, recorder) or emitted_any

    if token_record is not None:
        emitted_any = _emit_llm_metrics(invocation, token_record, recorder) or emitted_any

    if emitted_any:
        emitted_invocations.add(invocation.id)

    return emitted_any


def _emit_llm_metrics(
    invocation: Invocation,
    token_record: TokenUsageRecord,
    recorder: MetricsRecorder,
) -> bool:
    """Bridge LLM token and duration metrics from the database.

    The Temporal worker records these via ``record_llm_call`` in its own
    process memory.  This function re-emits them from persisted data so
    they appear in the API server's internal metrics store.
    """
    prompt_tokens = token_record.prompt_tokens or 0
    completion_tokens = token_record.completion_tokens or 0

    if prompt_tokens == 0 and completion_tokens == 0:
        return False

    model = invocation.model_name or "unknown"
    provider = model.split("/", 1)[0] if "/" in model else "unknown"
    status = "success" if invocation.status == InvocationStatus.COMPLETED else invocation.status.value
    llm_labels = {"model": model, "provider": provider, "status": status}

    if prompt_tokens > 0:
        recorder.record(
            MetricType.LLM_TOKENS_INPUT,
            float(prompt_tokens),
            unit="tokens",
            labels=llm_labels,
        )

    if completion_tokens > 0:
        recorder.record(
            MetricType.LLM_TOKENS_OUTPUT,
            float(completion_tokens),
            unit="tokens",
            labels=llm_labels,
        )

    # LLM_DURATION approximated from invocation wall-clock time
    if invocation.started_at and invocation.completed_at:
        duration_ms = (invocation.completed_at - invocation.started_at).total_seconds() * 1000
        recorder.record(MetricType.LLM_DURATION, duration_ms, unit="ms", labels=llm_labels)

    recorder.record(MetricType.LLM_STATUS, 1.0, labels=llm_labels)
    recorder.increment("llm_calls")
    return True


async def poll_completed_executions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Query for recent completions and emit their metrics.

    This is the callback invoked by ``PeriodicWorker`` each cycle.
    Covers both workflow/activity metrics (from Execution) and agent
    metrics (from Invocation).
    """
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.metrics_poller_lookback_seconds)
    recorder = get_metrics_recorder()

    # --- Workflow / activity metrics (existing) ---
    async with session_factory() as session:
        result = await session.exec(
            select(Execution)
            .where(Execution.status.in_(TERMINAL_EXECUTION_STATUSES))  # type: ignore[attr-defined]
            .where(Execution.completed_at >= cutoff)  # type: ignore[operator]
            .where(Execution.deleted_at.is_(None))  # type: ignore[union-attr]
            .options(selectinload(Execution.workflow))  # type: ignore[arg-type]
        )
        executions = result.all()

    exec_emitted = 0
    for execution in executions:
        async with session_factory() as session:
            if await emit_completion_metrics(session, execution, recorder):
                exec_emitted += 1

    # --- Agent & LLM metrics (bridged from Temporal worker) ---
    token_by_invocation: dict[UUID, TokenUsageRecord] = {}
    async with session_factory() as session:
        inv_result = await session.exec(
            select(Invocation)
            .where(Invocation.status.in_(TERMINAL_INVOCATION_STATUSES))  # type: ignore[attr-defined]
            .where(Invocation.completed_at >= cutoff)  # type: ignore[operator]
        )
        invocations = inv_result.all()

        inv_ids = [inv.id for inv in invocations if inv.id not in emitted_invocations]
        if inv_ids:
            token_result = await session.exec(
                select(TokenUsageRecord).where(
                    TokenUsageRecord.invocation_id.in_(inv_ids)  # type: ignore[union-attr]
                )
            )
            token_by_invocation = {r.invocation_id: r for r in token_result.all() if r.invocation_id is not None}

    inv_emitted = 0
    for invocation in invocations:
        token_record = token_by_invocation.get(invocation.id)
        if _emit_invocation_agent_metrics(invocation, recorder, token_record):
            inv_emitted += 1

    if exec_emitted or inv_emitted:
        logger.debug(
            "Completion poller emitted metrics",
            execution_count=exec_emitted,
            invocation_count=inv_emitted,
        )


def get_completion_poller() -> PeriodicWorker:
    """Return the application-wide completion-metrics PeriodicWorker."""
    settings = get_settings()
    return PeriodicWorker(
        name="metrics-completion-poller",
        interval_seconds=settings.metrics_poller_interval_seconds,
        session_factory=AsyncSessionLocal,
        callback=poll_completed_executions,
        coordinate=True,
    )
