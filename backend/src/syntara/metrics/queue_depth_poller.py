"""Background poller that emits Temporal task queue depth and active workflow metrics.

Periodically queries the Temporal server to obtain:

* **Queue depth** — via ``describe_task_queue`` for approximate backlog counts,
  recorded as ``TEMPORAL_QUEUE_DEPTH``.
* **Active workflows** — via ``count_workflows`` for the true number of
  currently running workflow executions, recorded as ``ACTIVE_WORKFLOWS``.
  This replaces the former in-process increment/decrement gauge which drifted
  on pod restarts.

Uses ``PeriodicWorker`` with ``coordinate=False`` so that every API-server
instance independently polls the same Temporal server; Prometheus handles
aggregation at scrape time.
"""

from __future__ import annotations

from typing import Any

import structlog
from temporalio.api.enums.v1 import TaskQueueKind, TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest
from temporalio.client import Client
from temporalio.service import RPCError

from syntara.core.config.base import get_settings
from syntara.core.tls.temporal import build_temporal_tls_config
from syntara.core.workers.periodic import PeriodicWorker
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.types import ComponentLabel, MetricType

logger = structlog.stdlib.get_logger(__name__)

_POLL_INTERVAL_SECONDS = 5.0

# Module-level client so the connection is established once and reused
# across polling cycles.
_temporal_client: Client | None = None


async def _ensure_client(address: str, namespace: str) -> Client | None:
    """Return a cached Temporal client, connecting on first call."""
    global _temporal_client  # noqa: PLW0603
    if _temporal_client is not None:
        return _temporal_client
    try:
        _temporal_client = await Client.connect(address, namespace=namespace, tls=build_temporal_tls_config())
    except (RPCError, OSError, RuntimeError):
        logger.warning(
            "queue_depth_poller_connect_failed",
            temporal_address=address,
            exc_info=True,
        )
        return None
    return _temporal_client


async def _query_queue_depth(client: Client, task_queue: str, namespace: str) -> int:
    """Query Temporal for the approximate backlog count on *task_queue*.

    Tries the ``report_stats`` field first (newer Temporal servers expose
    ``approximate_backlog_count``).  Falls back to the legacy
    ``include_task_queue_status`` / ``backlog_count_hint`` path.

    Returns 0 when the queue is empty or the server does not support
    either field.
    """
    req = DescribeTaskQueueRequest(
        namespace=namespace,
        task_queue=TaskQueue(name=task_queue, kind=TaskQueueKind.TASK_QUEUE_KIND_NORMAL),
        task_queue_type=TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW,
        report_stats=True,
        include_task_queue_status=True,
    )
    resp = await client.workflow_service.describe_task_queue(req)

    if resp.stats and resp.stats.approximate_backlog_count:
        return int(resp.stats.approximate_backlog_count)

    if resp.task_queue_status and resp.task_queue_status.backlog_count_hint:
        return int(resp.task_queue_status.backlog_count_hint)

    return 0


async def _query_running_workflow_count(client: Client) -> int:
    """Query Temporal for the number of currently running workflow executions.

    Uses the Temporal visibility ``count_workflows`` API with an
    ``ExecutionStatus='Running'`` filter.  This reflects the true cluster
    state and is not affected by pod restarts.
    """
    result = await client.count_workflows("ExecutionStatus='Running'")
    return result.count


def _make_poll_callback(
    temporal_address: str,
    namespace: str,
    task_queues: list[str],
) -> Any:  # noqa: ANN401
    """Build the async callback consumed by ``PeriodicWorker``.

    Each tick:

    1. Emits one ``TEMPORAL_QUEUE_DEPTH`` record per queue, labelled with the
       queue name so Prometheus can distinguish background-queue depth from
       workflow-queue depth when configuring HPA rules.
    2. Emits one ``ACTIVE_WORKFLOWS`` record with the true count of running
       workflow executions obtained from Temporal's visibility API.
    """

    async def _poll(_sf: object) -> None:
        client = await _ensure_client(temporal_address, namespace)
        if client is None:
            return
        recorder = get_metrics_recorder()
        for task_queue in task_queues:
            try:
                depth = await _query_queue_depth(client, task_queue, namespace)
            except RPCError:
                logger.debug("queue_depth_poller_rpc_error", task_queue=task_queue, exc_info=True)
                continue
            recorder.record(
                MetricType.TEMPORAL_QUEUE_DEPTH,
                float(depth),
                component=ComponentLabel.TEMPORAL_WORKER,
                labels={"task_queue": task_queue},
            )

        try:
            running_count = await _query_running_workflow_count(client)
        except RPCError:
            logger.debug("workflow_count_poller_rpc_error", exc_info=True)
            return
        recorder.record(
            MetricType.ACTIVE_WORKFLOWS,
            float(running_count),
            component=ComponentLabel.TEMPORAL_WORKER,
        )

    return _poll


def get_queue_depth_poller() -> PeriodicWorker:
    """Return a ``PeriodicWorker`` that polls Temporal queue depth for all task queues.

    Polls both the user workflow queue and the background queue so each can be
    targeted independently by Prometheus queries and HPA rules.
    """
    settings = get_settings()
    task_queues = list(dict.fromkeys([settings.task_queue, settings.background_task_queue]))
    return PeriodicWorker(
        name="temporal-queue-depth-poller",
        interval_seconds=_POLL_INTERVAL_SECONDS,
        callback=_make_poll_callback(
            temporal_address=settings.temporal_address,
            namespace=settings.temporal_namespace,
            task_queues=task_queues,
        ),
        coordinate=False,
    )
