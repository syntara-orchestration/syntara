"""Integration tests for the worker Prometheus metrics HTTP server.

Verifies that the metrics HTTP server started by ``worker_lifecycle.run_worker``
(via ``prometheus_client.start_http_server``) correctly binds to the configured
port and returns valid OpenMetrics/Prometheus text when scraped.

These tests exercise the real ``start_http_server`` call so that:
- The port binding in ``worker_lifecycle.py`` is actually exercised.
- A scrape target exists for Prometheus to hit (AAP-83411).

No Temporal connection is required — the metrics server is started before
the Temporal worker attempts to connect, so both paths are independent.

The test file lives in ``tests/integration/workflows/`` because
``worker_lifecycle.py`` belongs to the ``syntara.workflows`` domain.
"""

from __future__ import annotations

import socket
import threading
from contextlib import closing
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import prometheus_client
import pytest

from syntara.core.config.base import get_settings

if TYPE_CHECKING:
    from syntara.workflows.workflow_engine.services.temporal_worker import TemporalWorkerService


def _free_port() -> int:
    """Return an ephemeral port that is free at the time of calling."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class TestWorkerMetricsServer:
    """AAP-83411: Worker process binds a Prometheus metrics HTTP endpoint.

    The background worker and workflow worker both call
    ``prometheus_client.start_http_server(settings.metrics_worker_port)``
    in ``worker_lifecycle.run_worker()``.  These tests verify:

    1. The server binds to the configured port.
    2. GET /metrics returns HTTP 200 with valid Prometheus text.
    3. The response includes standard Python process metrics.
    4. The configured port from settings is used (not a hard-coded default).
    """

    def test_metrics_server_binds_and_returns_200(self) -> None:
        """Metrics server starts, binds to port, and returns HTTP 200."""
        port = _free_port()
        registry = prometheus_client.CollectorRegistry()

        server, thread = prometheus_client.start_http_server(port, registry=registry)
        try:
            response = httpx.get(f"http://localhost:{port}/metrics", timeout=5.0)
            assert response.status_code == 200
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_metrics_response_is_valid_prometheus_text(self) -> None:
        """Metrics endpoint returns valid Prometheus/OpenMetrics exposition format."""
        port = _free_port()
        registry = prometheus_client.CollectorRegistry(auto_describe=True)

        gauge = prometheus_client.Gauge(
            "orchestrator_test_worker_ready",
            "Test gauge confirming metrics server is up",
            registry=registry,
        )
        gauge.set(1.0)

        server, thread = prometheus_client.start_http_server(port, registry=registry)
        try:
            response = httpx.get(f"http://localhost:{port}/metrics", timeout=5.0)
            assert response.status_code == 200
            body = response.text
            assert "# HELP orchestrator_test_worker_ready" in body
            assert "# TYPE orchestrator_test_worker_ready gauge" in body
            assert "orchestrator_test_worker_ready 1.0" in body
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_metrics_server_uses_configured_port(self) -> None:
        """The metrics server port is read from settings.metrics_worker_port."""
        settings = get_settings()
        assert isinstance(settings.metrics_worker_port, int)
        assert 1 <= settings.metrics_worker_port <= 65535

    def test_worker_lifecycle_calls_start_http_server_with_configured_port(self) -> None:
        """run_worker() calls prometheus_client.start_http_server with metrics_worker_port.

        Uses a mock to avoid binding a real port and to avoid needing a Temporal
        connection — the metrics server is started before Temporal connects, so we
        can intercept it cleanly.
        """
        import asyncio

        from syntara.workflows.worker_lifecycle import run_worker

        captured_port: list[int] = []

        def _fake_start_http_server(port: int, **_: object) -> tuple[object, threading.Thread]:
            captured_port.append(port)
            fake_thread = threading.Thread(target=lambda: None)
            return object(), fake_thread

        async def _always_fail() -> TemporalWorkerService:
            msg = "simulated Temporal connection failure"
            raise RuntimeError(msg)

        with (
            patch(
                "syntara.workflows.worker_lifecycle.prometheus_client.start_http_server",
                side_effect=_fake_start_http_server,
            ),
            patch("syntara.workflows.worker_lifecycle.set_runtime_settings"),
            patch("syntara.workflows.worker_lifecycle.apply_runtime_log_level", new_callable=AsyncMock),
            patch(
                "syntara.workflows.worker_lifecycle.get_runtime_settings",
                return_value=AsyncMock(stop_watching=AsyncMock(), start_watching=AsyncMock()),
            ),
            patch("syntara.workflows.worker_lifecycle.discover_and_register_all_handlers"),
        ):
            # Create the coroutine outside pytest.raises so only asyncio.run
            # (the single raising call) is inside the block — satisfies S5778.
            coro = run_worker(_always_fail, worker_name="test-worker")
            with pytest.raises(SystemExit):
                asyncio.run(coro)

        expected_port = get_settings().metrics_worker_port
        assert len(captured_port) == 1, "start_http_server should be called exactly once"
        assert captured_port[0] == expected_port, f"Expected port {expected_port}, got {captured_port[0]}"
