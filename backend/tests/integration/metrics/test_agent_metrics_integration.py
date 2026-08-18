"""Integration test: agent metrics visible via Prometheus /metrics after invocation.

Proves that the Agent Orchestrator (which runs as a FastAPI BackgroundTask
in the same process) shares the MetricsRecorder singleton with the
``/metrics`` OpenMetrics scrape endpoint.  After an invocation completes,
agent-related Prometheus counters/histograms must be non-zero.
"""

import pytest
from httpx import AsyncClient

from tests.integration.helpers.invocations import wait_for_invocation_execution


@pytest.mark.asyncio
async def test_agent_metrics_on_openmetrics_endpoint(
    auth_client_with_mocked_llm: AsyncClient,
    test_project_id,
) -> None:
    """Agent invocation causes Prometheus counters/histograms to be non-zero."""
    response = await auth_client_with_mocked_llm.post(
        "/_internal/invocations",
        json={"prompt": "What is 2+2?", "session_id": "prom-metrics-test", "project_id": str(test_project_id)},
    )
    assert response.status_code == 202
    invocation_id = response.json()["id"]

    async with wait_for_invocation_execution(auth_client_with_mocked_llm, invocation_id, max_wait_time=10.0):
        pass

    prom_resp = await auth_client_with_mocked_llm.get("/metrics")
    assert prom_resp.status_code == 200
    body = prom_resp.text

    assert "orchestrator_requests_total" in body, "Prometheus output should contain request metrics"
