"""Unit tests for the MetricsMiddleware ASGI middleware.

Tests cover system overhead and error metrics:
- Total request duration recorded for every API request
- Component timing breakdown labels available
- Error counts by type (timeout, rate_limit, validation, internal)
- Error timestamps in labels
- Thread safety under concurrent requests
"""

import asyncio
from collections.abc import MutableMapping
from typing import Any
from unittest.mock import AsyncMock

import pytest
from prometheus_client import CollectorRegistry

from syntara.api.constants import EXCLUDED_PATHS
from syntara.metrics.interface_tag import INTERFACE_API, INTERFACE_UI, interface_context_var
from syntara.metrics.middleware import (
    MetricsMiddleware,
    classify_error_type,
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


def _make_scope(
    path: str = "/api/v1/workflows",
    method: str = "GET",
    scope_type: str = "http",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict[str, Any]:
    """Build a minimal ASGI scope dict."""
    return {
        "type": scope_type,
        "path": path,
        "method": method,
        "headers": headers or [],
    }


async def _make_app(status_code: int = 200, delay: float = 0.0) -> Any:  # noqa: ANN401
    """Create a fake ASGI app that sends a response with the given status."""

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
        if delay > 0:
            await asyncio.sleep(delay)
        await send({"type": "http.response.start", "status": status_code, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return app


# =============================================================================
# Error type classification
# =============================================================================


class TestClassifyErrorType:
    """Tests for classify_error_type helper."""

    def test_timeout_408(self) -> None:
        """HTTP 408 is classified as timeout."""
        assert classify_error_type(408) == "timeout"

    def test_timeout_504(self) -> None:
        """HTTP 504 is classified as timeout."""
        assert classify_error_type(504) == "timeout"

    def test_rate_limit_429(self) -> None:
        """HTTP 429 is classified as rate_limit."""
        assert classify_error_type(429) == "rate_limit"

    def test_validation_400(self) -> None:
        """HTTP 400 is classified as validation."""
        assert classify_error_type(400) == "validation"

    def test_validation_422(self) -> None:
        """HTTP 422 is classified as validation."""
        assert classify_error_type(422) == "validation"

    def test_internal_500(self) -> None:
        """HTTP 500 is classified as internal."""
        assert classify_error_type(500) == "internal"

    def test_internal_502(self) -> None:
        """HTTP 502 is classified as internal."""
        assert classify_error_type(502) == "internal"

    def test_internal_503(self) -> None:
        """HTTP 503 is classified as internal."""
        assert classify_error_type(503) == "internal"

    def test_client_error_fallback(self) -> None:
        """Other 4xx codes default to validation."""
        assert classify_error_type(403) == "validation"
        assert classify_error_type(404) == "validation"
        assert classify_error_type(405) == "validation"

    def test_server_error_fallback(self) -> None:
        """Other 5xx codes default to internal."""
        assert classify_error_type(501) == "internal"

    def test_success_returns_none(self) -> None:
        """Status codes below 400 return None."""
        assert classify_error_type(200) is None
        assert classify_error_type(201) is None
        assert classify_error_type(301) is None


# =============================================================================
# MetricsMiddleware - request duration recording
# =============================================================================


class TestMetricsMiddlewareRequestDuration:
    """Total request duration recorded for every API request."""

    @pytest.mark.asyncio
    async def test_records_request_duration(self, recorder: MetricsRecorder) -> None:
        """Every non-excluded HTTP request gets a REQUEST_DURATION metric."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        scope = _make_scope(path="/api/v1/workflows", method="GET")
        await middleware(scope, AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        assert len(results) == 1
        assert results[0].value >= 0
        assert results[0].unit == "ms"

    @pytest.mark.asyncio
    async def test_request_duration_labels(self, recorder: MetricsRecorder) -> None:
        """REQUEST_DURATION includes endpoint, method, and status labels."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        scope = _make_scope(path="/api/v1/workflows", method="POST")
        await middleware(scope, AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        assert len(results) == 1
        labels = results[0].labels
        assert labels["endpoint"] == "/api/v1/workflows"
        assert labels["method"] == "POST"
        assert labels["status"] == "200"

    @pytest.mark.asyncio
    async def test_duration_is_positive(self, recorder: MetricsRecorder) -> None:
        """Recorded duration is a positive value in milliseconds."""
        app = await _make_app(status_code=200, delay=0.01)
        middleware = MetricsMiddleware(app, recorder=recorder)

        scope = _make_scope()
        await middleware(scope, AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        assert results[0].value >= 5

    @pytest.mark.asyncio
    async def test_increments_requests_counter(self, recorder: MetricsRecorder) -> None:
        """Each request increments the 'requests' summary counter."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        for _ in range(3):
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        assert recorder.get_summary().total_requests == 3

    @pytest.mark.asyncio
    async def test_uses_route_template_as_endpoint_label(self, recorder: MetricsRecorder) -> None:
        """When Starlette resolves a route, the template is used instead of the raw path."""

        class _FakeRoute:
            path = "/api/v1/executions/{execution_id}"

        async def app_with_route(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            scope["route"] = _FakeRoute()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = MetricsMiddleware(app_with_route, recorder=recorder)  # type: ignore[arg-type]
        scope = _make_scope(path="/api/v1/executions/3f129c38-1008-4383-a224-e20ddcf51755")
        await middleware(scope, AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        assert results[0].labels["endpoint"] == "/api/v1/executions/{execution_id}"

    @pytest.mark.asyncio
    async def test_falls_back_to_raw_path_when_no_route(self, recorder: MetricsRecorder) -> None:
        """Without a resolved route (e.g. 404), the raw path is used as endpoint label."""
        app = await _make_app(status_code=404)
        middleware = MetricsMiddleware(app, recorder=recorder)

        scope = _make_scope(path="/api/v1/nonexistent")
        await middleware(scope, AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        assert results[0].labels["endpoint"] == "/api/v1/nonexistent"


# =============================================================================
# MetricsMiddleware - error metrics
# =============================================================================


class TestMetricsMiddlewareErrors:
    """Error counts recorded with error_type label."""

    @pytest.mark.asyncio
    async def test_error_recorded_for_4xx(self, recorder: MetricsRecorder) -> None:
        """4xx responses record an ERROR metric."""
        app = await _make_app(status_code=400)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        errors = list(recorder.query(metric_types={MetricType.ERROR}))
        assert len(errors) == 1
        assert errors[0].labels["error_type"] == "validation"

    @pytest.mark.asyncio
    async def test_error_recorded_for_5xx(self, recorder: MetricsRecorder) -> None:
        """5xx responses record an ERROR metric with 'internal' type."""
        app = await _make_app(status_code=500)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        errors = list(recorder.query(metric_types={MetricType.ERROR}))
        assert len(errors) == 1
        assert errors[0].labels["error_type"] == "internal"

    @pytest.mark.asyncio
    async def test_error_includes_endpoint_and_method(self, recorder: MetricsRecorder) -> None:
        """Error metrics include endpoint and method labels."""
        app = await _make_app(status_code=422)
        middleware = MetricsMiddleware(app, recorder=recorder)

        scope = _make_scope(path="/api/v1/invocations", method="POST")
        await middleware(scope, AsyncMock(), AsyncMock())

        errors = list(recorder.query(metric_types={MetricType.ERROR}))
        assert errors[0].labels["endpoint"] == "/api/v1/invocations"
        assert errors[0].labels["method"] == "POST"

    @pytest.mark.asyncio
    async def test_error_increments_errors_counter(self, recorder: MetricsRecorder) -> None:
        """Error responses increment the 'errors' summary counter."""
        app = await _make_app(status_code=500)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())
        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        assert recorder.get_summary().total_errors == 2

    @pytest.mark.asyncio
    async def test_no_error_recorded_for_2xx(self, recorder: MetricsRecorder) -> None:
        """Successful responses do not produce ERROR metrics."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        errors = list(recorder.query(metric_types={MetricType.ERROR}))
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_rate_limit_error_type(self, recorder: MetricsRecorder) -> None:
        """429 responses are classified as rate_limit."""
        app = await _make_app(status_code=429)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        errors = list(recorder.query(metric_types={MetricType.ERROR}))
        assert errors[0].labels["error_type"] == "rate_limit"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [408, 504])
    async def test_timeout_error_type(self, status_code: int) -> None:
        """Timeout status codes are classified as timeout."""
        rec = MetricsRecorder(
            retention_seconds=3600,
            max_records=10_000,
            prometheus_registry=CollectorRegistry(),
        )
        app = await _make_app(status_code=status_code)
        mw = MetricsMiddleware(app, recorder=rec)

        await mw(_make_scope(), AsyncMock(), AsyncMock())

        errors = list(rec.query(metric_types={MetricType.ERROR}))
        assert errors[0].labels["error_type"] == "timeout"


# =============================================================================
# MetricsMiddleware - system-wide metrics (FR-021/FR-022)
# =============================================================================


class TestMetricsMiddlewareSystemWide:
    """System-wide metrics: E2E latency, error rate, and uptime."""

    @pytest.mark.asyncio
    async def test_e2e_latency_recorded(self, recorder: MetricsRecorder) -> None:
        """SYSTEM_E2E_LATENCY is recorded for every request."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.SYSTEM_E2E_LATENCY}))
        assert len(results) == 1
        assert results[0].value >= 0
        assert results[0].labels["component"] == "system_wide"

    @pytest.mark.asyncio
    async def test_uptime_recorded_on_error(self, recorder: MetricsRecorder) -> None:
        """SYSTEM_UPTIME is always recorded on error responses."""
        app = await _make_app(status_code=500)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.SYSTEM_UPTIME}))
        assert len(results) == 1
        assert results[0].value >= 0

    @pytest.mark.asyncio
    async def test_uptime_not_recorded_on_single_success(self, recorder: MetricsRecorder) -> None:
        """SYSTEM_UPTIME is not recorded on a single success request (sampled every Nth)."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.SYSTEM_UPTIME}))
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_uptime_sampled_periodically(self, recorder: MetricsRecorder) -> None:
        """SYSTEM_UPTIME is recorded every _UPTIME_SAMPLE_INTERVAL requests during healthy traffic."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        interval = MetricsMiddleware._UPTIME_SAMPLE_INTERVAL
        for _ in range(interval):
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.SYSTEM_UPTIME}))
        assert len(results) == 1
        assert results[0].value >= 0

    @pytest.mark.asyncio
    async def test_error_rate_not_recorded_on_success(self, recorder: MetricsRecorder) -> None:
        """SYSTEM_ERROR_RATE is not recorded on success-only requests."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.SYSTEM_ERROR_RATE}))
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_error_rate_after_mixed_requests(self, recorder: MetricsRecorder) -> None:
        """SYSTEM_ERROR_RATE reflects the running error ratio on error requests."""
        ok_app = await _make_app(status_code=200)
        err_app = await _make_app(status_code=500)

        ok_mw = MetricsMiddleware(ok_app, recorder=recorder)
        err_mw = MetricsMiddleware(err_app, recorder=recorder)

        await ok_mw(_make_scope(), AsyncMock(), AsyncMock())
        await ok_mw(_make_scope(), AsyncMock(), AsyncMock())
        await err_mw(_make_scope(), AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.SYSTEM_ERROR_RATE}))
        assert len(results) == 1
        assert results[0].value == pytest.approx(1.0 / 3.0)

    @pytest.mark.asyncio
    async def test_e2e_latency_updates_prometheus_histogram(self, recorder: MetricsRecorder) -> None:
        """SYSTEM_E2E_LATENCY updates the Prometheus histogram."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        sample_sum = recorder.prometheus.system_e2e_latency_seconds.labels(
            component="system_wide",
        )._sum.get()
        assert sample_sum > 0


# =============================================================================
# MetricsMiddleware - Prometheus integration
# =============================================================================


class TestMetricsMiddlewarePrometheus:
    """Verify Prometheus counters are updated by the middleware."""

    @pytest.mark.asyncio
    async def test_requests_total_incremented(self, recorder: MetricsRecorder) -> None:
        """orchestrator_requests_total Prometheus counter is incremented."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(
            _make_scope(path="/api/v1/test"),
            AsyncMock(),
            AsyncMock(),
        )

        value = recorder.prometheus.requests_total.labels(
            status="200",
            endpoint="/api/v1/test",
            interface="api",
        )._value.get()
        assert value == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_errors_total_incremented(self, recorder: MetricsRecorder) -> None:
        """orchestrator_errors_total Prometheus counter is incremented for errors."""
        app = await _make_app(status_code=500)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        value = recorder.prometheus.errors_total.labels(
            error_type="internal",
            interface="api",
        )._value.get()
        assert value == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_request_duration_histogram_updated(self, recorder: MetricsRecorder) -> None:
        """orchestrator_request_duration_seconds histogram is observed."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(
            _make_scope(path="/api/v1/test"),
            AsyncMock(),
            AsyncMock(),
        )

        sample_sum = recorder.prometheus.request_duration_seconds.labels(
            endpoint="/api/v1/test",
            method="GET",
            interface="api",
        )._sum.get()
        assert sample_sum > 0


# =============================================================================
# MetricsMiddleware - exclusions
# =============================================================================


class TestMetricsMiddlewareExclusions:
    """Verify that excluded paths and non-HTTP scopes are skipped."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", sorted(EXCLUDED_PATHS))
    async def test_excluded_paths_not_recorded(self, path: str, recorder: MetricsRecorder) -> None:
        """Excluded endpoint is not instrumented."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(path=path), AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_non_http_scope_passthrough(self, recorder: MetricsRecorder) -> None:
        """WebSocket and other non-HTTP scopes pass through without metrics."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        scope = _make_scope(scope_type="websocket")
        await middleware(scope, AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_excluded_path_strips_auth_failure_header(self, recorder: MetricsRecorder) -> None:
        """X-Auth-Failure-Type header is stripped even on excluded paths."""
        captured_headers: list[tuple[bytes, bytes]] = []

        async def auth_failure_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"x-auth-failure-type", b"stale_token"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        async def capturing_send(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                captured_headers.extend(message.get("headers", []))

        middleware = MetricsMiddleware(auth_failure_app, recorder=recorder)  # type: ignore[arg-type]
        await middleware(_make_scope(path="/health"), AsyncMock(), capturing_send)

        header_names = [name for name, _ in captured_headers]
        assert b"x-auth-failure-type" not in header_names
        assert b"content-type" in header_names

    @pytest.mark.asyncio
    async def test_excluded_paths_still_pass_to_app(self, recorder: MetricsRecorder) -> None:
        """Excluded paths are still forwarded to the underlying app."""
        call_count = 0

        async def counting_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            nonlocal call_count
            call_count += 1

        middleware = MetricsMiddleware(counting_app, recorder=recorder)  # type: ignore[arg-type]
        await middleware(_make_scope(path="/health"), AsyncMock(), AsyncMock())

        assert call_count == 1


# =============================================================================
# MetricsMiddleware - disabled recorder
# =============================================================================


class TestMetricsMiddlewareDisabled:
    """When recorder is disabled, middleware still forwards requests."""

    @pytest.mark.asyncio
    async def test_disabled_recorder_no_metrics(self) -> None:
        """Disabled recorder produces no metric records."""
        disabled = MetricsRecorder(
            prometheus_registry=CollectorRegistry(),
            enabled=False,
        )
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=disabled)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        assert disabled.store.count() == 0

    @pytest.mark.asyncio
    async def test_disabled_recorder_still_forwards(self) -> None:
        """Even with disabled recorder, requests reach the app."""
        disabled = MetricsRecorder(
            prometheus_registry=CollectorRegistry(),
            enabled=False,
        )
        call_count = 0

        async def counting_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            nonlocal call_count
            call_count += 1

        middleware = MetricsMiddleware(counting_app, recorder=disabled)  # type: ignore[arg-type]
        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        assert call_count == 1


# =============================================================================
# MetricsMiddleware - exception handling
# =============================================================================


class TestMetricsMiddlewareExceptions:
    """Middleware records metrics even when the app raises."""

    @pytest.mark.asyncio
    async def test_records_duration_on_app_exception(self, recorder: MetricsRecorder) -> None:
        """Request duration is recorded even if the app raises an exception."""
        msg = "unexpected"

        async def raising_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            raise RuntimeError(msg)

        middleware = MetricsMiddleware(raising_app, recorder=recorder)  # type: ignore[arg-type]

        with pytest.raises(RuntimeError, match=msg):
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        assert len(results) == 1
        assert results[0].labels["status"] == "500"

    @pytest.mark.asyncio
    async def test_error_recorded_on_app_exception(self, recorder: MetricsRecorder) -> None:
        """An ERROR metric is recorded when the app raises."""
        msg = "crash"

        async def raising_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            raise RuntimeError(msg)

        middleware = MetricsMiddleware(raising_app, recorder=recorder)  # type: ignore[arg-type]

        with pytest.raises(RuntimeError, match=msg):
            await middleware(_make_scope(), AsyncMock(), AsyncMock())

        errors = list(recorder.query(metric_types={MetricType.ERROR}))
        assert len(errors) == 1
        assert errors[0].labels["error_type"] == "internal"


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestMetricsMiddlewareThreadSafety:
    """Verify that concurrent requests don't corrupt shared recorder state."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_no_lost_counts(self, recorder: MetricsRecorder) -> None:
        """Concurrent requests must not lose request/error counts."""
        n_ok = 50
        n_err = 50

        ok_app = await _make_app(status_code=200)
        err_app = await _make_app(status_code=500)

        ok_mw = MetricsMiddleware(ok_app, recorder=recorder)
        err_mw = MetricsMiddleware(err_app, recorder=recorder)

        tasks = [
            asyncio.create_task(ok_mw(_make_scope(path=f"/api/v1/t/{i}"), AsyncMock(), AsyncMock()))
            for i in range(n_ok)
        ] + [
            asyncio.create_task(err_mw(_make_scope(path=f"/api/v1/t/{i}"), AsyncMock(), AsyncMock()))
            for i in range(n_err)
        ]
        await asyncio.gather(*tasks)

        summary = recorder.get_summary()
        assert summary.total_requests == n_ok + n_err
        assert summary.total_errors == n_err

        durations = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        assert len(durations) == n_ok + n_err

    @pytest.mark.asyncio
    async def test_concurrent_error_rate_within_bounds(self, recorder: MetricsRecorder) -> None:
        """Error rate recorded under concurrency stays within valid bounds."""
        ok_app = await _make_app(status_code=200)
        err_app = await _make_app(status_code=500)

        ok_mw = MetricsMiddleware(ok_app, recorder=recorder)
        err_mw = MetricsMiddleware(err_app, recorder=recorder)

        tasks = [asyncio.create_task(ok_mw(_make_scope(), AsyncMock(), AsyncMock())) for _ in range(30)] + [
            asyncio.create_task(err_mw(_make_scope(), AsyncMock(), AsyncMock())) for _ in range(20)
        ]
        await asyncio.gather(*tasks)

        error_rates = list(recorder.query(metric_types={MetricType.SYSTEM_ERROR_RATE}))
        for r in error_rates:
            assert 0.0 <= r.value <= 1.0, f"Error rate {r.value} out of bounds"


# =============================================================================
# MetricsMiddleware - interface tagging (AAP-77419)
# =============================================================================


class TestMetricsMiddlewareInterfaceTagging:
    """Verify interface label (api/ui) is applied to all recorded metrics."""

    @pytest.mark.asyncio
    async def test_default_interface_is_api(self, recorder: MetricsRecorder) -> None:
        """Requests without X-Orchestrator-Client header get interface=api."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        assert results[0].labels["interface"] == INTERFACE_API

    @pytest.mark.asyncio
    async def test_ui_header_sets_interface_ui(self, recorder: MetricsRecorder) -> None:
        """Requests with X-Orchestrator-Client: ui get interface=ui."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        scope = _make_scope(headers=[(b"x-orchestrator-client", b"ui")])
        await middleware(scope, AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        assert results[0].labels["interface"] == INTERFACE_UI

    @pytest.mark.asyncio
    async def test_interface_label_on_error_metrics(self, recorder: MetricsRecorder) -> None:
        """Error metrics also carry the interface label."""
        app = await _make_app(status_code=500)
        middleware = MetricsMiddleware(app, recorder=recorder)

        scope = _make_scope(headers=[(b"x-orchestrator-client", b"ui")])
        await middleware(scope, AsyncMock(), AsyncMock())

        errors = list(recorder.query(metric_types={MetricType.ERROR}))
        assert len(errors) == 1
        assert errors[0].labels["interface"] == INTERFACE_UI

    @pytest.mark.asyncio
    async def test_interface_context_var_set_for_downstream(self, recorder: MetricsRecorder) -> None:
        """The interface ContextVar is set so downstream code can read it."""
        captured_interface: str | None = None

        async def capturing_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            nonlocal captured_interface
            captured_interface = interface_context_var.get()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = MetricsMiddleware(capturing_app, recorder=recorder)  # type: ignore[arg-type]
        scope = _make_scope(headers=[(b"x-orchestrator-client", b"ui")])
        await middleware(scope, AsyncMock(), AsyncMock())

        assert captured_interface == INTERFACE_UI

    @pytest.mark.asyncio
    async def test_api_interface_context_var_for_no_header(self, recorder: MetricsRecorder) -> None:
        """Without the header, ContextVar is set to 'api'."""
        captured_interface: str | None = None

        async def capturing_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            nonlocal captured_interface
            captured_interface = interface_context_var.get()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = MetricsMiddleware(capturing_app, recorder=recorder)  # type: ignore[arg-type]
        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        assert captured_interface == INTERFACE_API

    @pytest.mark.asyncio
    async def test_interface_label_on_exception(self, recorder: MetricsRecorder) -> None:
        """Interface label is recorded even when the app raises."""
        msg = "boom"

        async def raising_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            raise RuntimeError(msg)

        middleware = MetricsMiddleware(raising_app, recorder=recorder)  # type: ignore[arg-type]
        scope = _make_scope(headers=[(b"x-orchestrator-client", b"ui")])

        receive, send = AsyncMock(), AsyncMock()
        with pytest.raises(RuntimeError, match=msg):
            await middleware(scope, receive, send)

        results = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        assert results[0].labels["interface"] == INTERFACE_UI

    @pytest.mark.asyncio
    async def test_existing_labels_preserved_with_interface(self, recorder: MetricsRecorder) -> None:
        """All existing labels (endpoint, method, status) are still present alongside interface."""
        app = await _make_app(status_code=201)
        middleware = MetricsMiddleware(app, recorder=recorder)

        scope = _make_scope(path="/api/v1/workflows", method="POST", headers=[(b"x-orchestrator-client", b"ui")])
        await middleware(scope, AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.REQUEST_DURATION}))
        labels = results[0].labels
        assert labels["endpoint"] == "/api/v1/workflows"
        assert labels["method"] == "POST"
        assert labels["status"] == "201"
        assert labels["interface"] == INTERFACE_UI


# =============================================================================
# MetricsMiddleware - auth failure recording (AAP-77261)
# =============================================================================


class TestMetricsMiddlewareAuthFailure:
    """Verify auth failure metrics are recorded from X-Auth-Failure-Type response header."""

    @pytest.mark.asyncio
    async def test_auth_failure_recorded_from_response_header(self, recorder: MetricsRecorder) -> None:
        """When inner app sets X-Auth-Failure-Type header, AUTH_FAILURE metric is recorded."""

        async def auth_failure_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"x-auth-failure-type", b"expired_token")],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        middleware = MetricsMiddleware(auth_failure_app, recorder=recorder)  # type: ignore[arg-type]
        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.AUTH_FAILURE}))
        assert len(results) == 1
        assert results[0].labels["failure_type"] == "expired_token"
        assert results[0].labels["interface"] == INTERFACE_API

    @pytest.mark.asyncio
    async def test_auth_failure_with_ui_interface(self, recorder: MetricsRecorder) -> None:
        """Auth failure metric includes the interface from the request header."""

        async def auth_failure_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"x-auth-failure-type", b"invalid_token")],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        middleware = MetricsMiddleware(auth_failure_app, recorder=recorder)  # type: ignore[arg-type]
        scope = _make_scope(headers=[(b"x-orchestrator-client", b"ui")])
        await middleware(scope, AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.AUTH_FAILURE}))
        assert len(results) == 1
        assert results[0].labels["failure_type"] == "invalid_token"
        assert results[0].labels["interface"] == INTERFACE_UI

    @pytest.mark.asyncio
    async def test_no_auth_failure_on_success(self, recorder: MetricsRecorder) -> None:
        """No AUTH_FAILURE metric when authentication succeeds."""
        app = await _make_app(status_code=200)
        middleware = MetricsMiddleware(app, recorder=recorder)

        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        results = list(recorder.query(metric_types={MetricType.AUTH_FAILURE}))
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_auth_failure_header_stripped_from_response(self, recorder: MetricsRecorder) -> None:
        """X-Auth-Failure-Type header is stripped and not sent to the client."""
        captured_headers: list[tuple[bytes, bytes]] = []

        async def auth_failure_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"x-auth-failure-type", b"expired_token"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        async def capturing_send(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                captured_headers.extend(message.get("headers", []))

        middleware = MetricsMiddleware(auth_failure_app, recorder=recorder)  # type: ignore[arg-type]
        await middleware(_make_scope(), AsyncMock(), capturing_send)

        header_names = [name for name, _ in captured_headers]
        assert b"x-auth-failure-type" not in header_names
        assert b"content-type" in header_names

    @pytest.mark.asyncio
    async def test_401_auth_failure_does_not_double_count_error(self, recorder: MetricsRecorder) -> None:
        """A 401 with X-Auth-Failure-Type records AUTH_FAILURE but not ERROR."""

        async def auth_failure_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"x-auth-failure-type", b"expired_token")],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        middleware = MetricsMiddleware(auth_failure_app, recorder=recorder)  # type: ignore[arg-type]
        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        auth_failures = list(recorder.query(metric_types={MetricType.AUTH_FAILURE}))
        assert len(auth_failures) == 1

        errors = list(recorder.query(metric_types={MetricType.ERROR}))
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_403_csrf_records_auth_failure(self, recorder: MetricsRecorder) -> None:
        """A 403 CSRF failure with X-Auth-Failure-Type records AUTH_FAILURE."""

        async def csrf_failure_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"x-auth-failure-type", b"csrf_failed")],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        middleware = MetricsMiddleware(csrf_failure_app, recorder=recorder)  # type: ignore[arg-type]
        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        auth_failures = list(recorder.query(metric_types={MetricType.AUTH_FAILURE}))
        assert len(auth_failures) == 1
        assert auth_failures[0].labels["failure_type"] == "csrf_failed"

    @pytest.mark.asyncio
    async def test_auth_failure_prometheus_counter(self, recorder: MetricsRecorder) -> None:
        """AUTH_FAILURE metric updates the Prometheus auth_failures_total counter."""

        async def auth_failure_app(scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"x-auth-failure-type", b"missing_credentials")],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        middleware = MetricsMiddleware(auth_failure_app, recorder=recorder)  # type: ignore[arg-type]
        await middleware(_make_scope(), AsyncMock(), AsyncMock())

        value = recorder.prometheus.auth_failures_total.labels(
            failure_type="missing_credentials", interface="api"
        )._value.get()
        assert value == pytest.approx(1.0)
