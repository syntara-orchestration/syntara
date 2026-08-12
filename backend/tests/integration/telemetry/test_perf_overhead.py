"""Performance test for telemetry overhead (SC-002).

Validates that telemetry event collection and transmission adds less than
5% overhead to workflow-equivalent operations.

The Segment client is initialized with an invalid write key and an
endpoint on localhost that refuses connections immediately.  This
exercises the full SDK code path (serialization, batching, queuing)
without mocking, while ensuring the consumer threads never block on
TCP timeouts so ``shutdown()`` returns promptly.

Each iteration executes real ``execute_bash_script`` activities (subprocess
creation, Pydantic config validation, template resolution, env setup) so
the baseline faithfully represents the actual cost of workflow activity
execution.

Run with: make test-integration-coverage
"""

import os
import statistics
import time
import uuid
from unittest.mock import patch

import pytest
import structlog

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.telemetry.client import TelemetryClientRegistry
from syntara.telemetry.events.workflow_execution import (
    WorkflowExecutionCompletedEvent,
    WorkflowExecutionStartEvent,
)
from syntara.telemetry.handlers.node_execution import NodeExecutedTelemetryHandler
from syntara.workflows.audit.node_execution import NodeExecutedEvent
from syntara.workflows.workflow_engine.activities.script_activity import execute_script_activity
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ActivityTerminalStatus,
    NodeType,
    WorkflowTerminalStatus,
)

logger = structlog.stdlib.get_logger(__name__)

# Number of simulated workflow executions per measurement
_ITERATIONS = 50

# SC-002 overhead threshold (%). Defaults to 5% (production SLO).
# CI sets SYNTARA_TELEMETRY_OVERHEAD_THRESHOLD_PCT=50 to accommodate shared
# runner variability while still catching catastrophic regressions.
_OVERHEAD_THRESHOLD_PCT = float(os.environ.get("SYNTARA_TELEMETRY_OVERHEAD_THRESHOLD_PCT", "5.0"))

# Activities per workflow execution
_ACTIVITIES_PER_WORKFLOW = 5

# Activity definitions used for telemetry event construction.
_ACTIVITY_DEFS: list[dict[str, object]] = [
    {
        "id": f"step-{i}",
        "type": "script",
        "parameters": {"language": "bash", "code": "echo ok"},
    }
    for i in range(_ACTIVITIES_PER_WORKFLOW)
]

# Script activity config passed to execute_script_activity.
# The script performs a SHA-256 hash computation to simulate a lightweight
# but realistic workload.  Real activities (API calls, AAP job templates)
# take 100 ms to minutes; this is intentionally fast to stress the overhead
# measurement while remaining representative of actual subprocess work.
_SCRIPT_CONFIG: dict[str, str] = {
    "language": "bash",
    "code": 'for i in $(seq 1 5); do echo "payload-$i" | sha256sum > /dev/null; done',
}


async def _run_workflow_activities() -> None:
    """Execute real bash script activities like a workflow would."""
    for _ in range(_ACTIVITIES_PER_WORKFLOW):
        await execute_script_activity(_SCRIPT_CONFIG, None)


async def _run_baseline(iterations: int) -> list[float]:
    """Run workflow activities without telemetry."""
    latencies: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        await _run_workflow_activities()
        latencies.append((time.perf_counter() - start) * 1000)
    return latencies


async def _run_with_telemetry(registry: TelemetryClientRegistry, iterations: int) -> list[float]:
    """Run workflow activities with telemetry event emission."""
    latencies: list[float] = []
    for _ in range(iterations):
        wf_id = uuid.uuid4()

        start = time.perf_counter()

        registry.send_event(
            WorkflowExecutionStartEvent(
                workflow_execution_id=str(wf_id),
                entitlement_id=registry.entitlement_id,
            )
        )
        await _run_workflow_activities()

        for i in range(_ACTIVITIES_PER_WORKFLOW):
            AuditEventDispatcher.dispatch(
                NodeExecutedEvent(
                    execution_id=wf_id,
                    node_type=NodeType.SCRIPT,
                    node_def=_ACTIVITY_DEFS[i],
                    status=ActivityTerminalStatus.COMPLETED,
                    duration_ms=10,
                )
            )
        registry.send_event(
            WorkflowExecutionCompletedEvent(
                workflow_execution_id=str(wf_id),
                status=WorkflowTerminalStatus.COMPLETED,
                duration_ms=50,
                node_count=_ACTIVITIES_PER_WORKFLOW,
                error_count=0,
                entitlement_id=registry.entitlement_id,
            )
        )

        latencies.append((time.perf_counter() - start) * 1000)
    return latencies


class TestTelemetryOverhead:
    """Validate telemetry adds <5% overhead (SC-002)."""

    @pytest.mark.asyncio
    async def test_telemetry_overhead_below_threshold(self) -> None:
        """Telemetry overhead must stay below 5% of baseline execution time."""
        # Use a real Segment client with bogus credentials.
        # localhost:1 gives instant "Connection refused" so the SDK
        # never blocks on TCP timeouts.  We also override retries and
        # upload_interval so consumer threads drain the queue quickly
        # and shutdown() returns without delay.
        registry = TelemetryClientRegistry()
        registry.initialize(
            write_key="invalid-key",
            host="http://127.0.0.1:1",
            entitlement_id="perf-test",
        )
        client = registry.get_client()
        # Disable retries so failed sends return immediately and the
        # consumer thread never blocks during shutdown().
        client.max_retries = 0
        for consumer in client.consumers:
            consumer.retries = 0

        AuditEventDispatcher.register({NodeExecutedEvent: NodeExecutedTelemetryHandler()})

        with patch("temporalio.activity.heartbeat"):
            try:
                # Warmup
                await _run_baseline(5)
                await _run_with_telemetry(registry, 5)

                # Measure
                baseline = await _run_baseline(_ITERATIONS)
                with_telemetry = await _run_with_telemetry(registry, _ITERATIONS)

                mean_baseline = statistics.mean(baseline)
                mean_telemetry = statistics.mean(with_telemetry)
                overhead_pct = ((mean_telemetry - mean_baseline) / mean_baseline) * 100

                baseline_p95 = sorted(baseline)[int(0.95 * len(baseline))]
                telemetry_p95 = sorted(with_telemetry)[int(0.95 * len(with_telemetry))]

                logger.info(
                    "Telemetry overhead test results (SC-002)",
                    iterations=_ITERATIONS,
                    baseline_mean_ms=round(mean_baseline, 3),
                    baseline_p95_ms=round(baseline_p95, 3),
                    telemetry_mean_ms=round(mean_telemetry, 3),
                    telemetry_p95_ms=round(telemetry_p95, 3),
                    overhead_pct=round(overhead_pct, 2),
                    threshold_pct=_OVERHEAD_THRESHOLD_PCT,
                )

                diag = (
                    f"\n--- Telemetry overhead results (SC-002) ---\n"
                    f"  iterations={_ITERATIONS}\n"
                    f"  baseline: mean={mean_baseline:.3f}ms, p95={baseline_p95:.3f}ms\n"
                    f"  telemetry: mean={mean_telemetry:.3f}ms, p95={telemetry_p95:.3f}ms\n"
                    f"  overhead={overhead_pct:.2f}%\n"
                )

                assert overhead_pct < _OVERHEAD_THRESHOLD_PCT, (
                    f"Telemetry overhead {overhead_pct:.2f}% exceeds {_OVERHEAD_THRESHOLD_PCT:.0f}% threshold{diag}"
                )
            finally:
                registry.get_client().shutdown()
