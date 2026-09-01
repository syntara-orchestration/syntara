"""ASGI metrics middleware for system overhead and error instrumentation.

Records per-request metrics:

* Total request duration for every API request.
* Component timing breakdown labels (endpoint, method).
* Error counts categorised by type (timeout, rate_limit, validation, internal).
"""

from __future__ import annotations

import gc
import time
from typing import TYPE_CHECKING

import structlog

from syntara.api.constants import EXCLUDED_PATH_PREFIXES, EXCLUDED_PATHS
from syntara.audit.emitter import request_id_context_var
from syntara.metrics.cleanup import release_memory_to_os
from syntara.metrics.interface_tag import detect_interface, interface_context_var
from syntara.metrics.types import ComponentLabel, MetricType

if TYPE_CHECKING:
    from uuid import UUID

    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from syntara.metrics.recorder import MetricsRecorder

logger = structlog.stdlib.get_logger(__name__)

_REQUEST_ID_HEADER: bytes = b"x-request-id"
_AUTH_FAILURE_HEADER: bytes = b"x-auth-failure-type"

# ---- Error type classification -------------------------------------------------

_TIMEOUT_CODES: frozenset[int] = frozenset({408, 504})
_RATE_LIMIT_CODES: frozenset[int] = frozenset({429})


def classify_error_type(status_code: int) -> str | None:
    """Classify an HTTP status code into an error type label.

    Returns one of ``"timeout"``, ``"rate_limit"``, ``"validation"``,
    ``"internal"``, or ``None`` for non-error status codes (< 400).

    Args:
        status_code: HTTP response status code.

    Returns:
        Error type string or ``None`` for success responses.

    """
    if status_code < 400:  # noqa: PLR2004
        return None
    if status_code in _TIMEOUT_CODES:
        return "timeout"
    if status_code in _RATE_LIMIT_CODES:
        return "rate_limit"
    if 400 <= status_code < 500:  # noqa: PLR2004
        return "validation"
    return "internal"


# ---- Route resolution -----------------------------------------------------------


def _resolve_endpoint(scope: Scope, raw_path: str) -> str:
    """Extract the route template from the ASGI scope for use as a metric label.

    Starlette populates ``scope["route"]`` after routing completes.  Using
    the template (e.g. ``/api/v1/executions/{execution_id}``) instead of the
    raw path avoids unbounded label cardinality in Prometheus.

    Falls back to *raw_path* when no route is resolved (e.g. 404 responses).
    """
    route = scope.get("route")
    if route is not None and hasattr(route, "path"):
        return route.path  # type: ignore[no-any-return]
    return raw_path


# ---- Middleware ------------------------------------------------------------------


def _process_response_headers(
    headers: list[tuple[bytes, bytes]],
    request_id: UUID | None,
) -> tuple[list[tuple[bytes, bytes]], str | None]:
    """Inject request-id header and extract/strip the auth-failure signaling header."""
    if request_id is not None:
        headers.append((_REQUEST_ID_HEADER, str(request_id).encode()))
    auth_failure_type: str | None = None
    filtered: list[tuple[bytes, bytes]] = []
    for name, value in headers:
        if name == _AUTH_FAILURE_HEADER:
            auth_failure_type = value.decode("latin-1")
        else:
            filtered.append((name, value))
    return filtered, auth_failure_type


class MetricsMiddleware:
    """ASGI middleware that records request duration and error metrics.

    For every non-excluded HTTP request the middleware:

    1. Times the full request lifecycle.
    2. Records a ``REQUEST_DURATION`` metric with endpoint, method, status, and
       interface labels.
    3. For error responses (>= 400), records an ``ERROR`` metric with the
       classified ``error_type`` and interface label.
    4. Injects the ``X-Request-Id`` response header when present.

    Args:
        app: The next ASGI application in the chain.
        recorder: The :class:`MetricsRecorder` to record metrics to.

    """

    _UPTIME_SAMPLE_INTERVAL: int = 100
    _MEMORY_TRIM_INTERVAL: int = 50

    def __init__(self, app: ASGIApp, recorder: MetricsRecorder) -> None:
        """Initialise the middleware.

        Args:
            app: The next ASGI application in the chain.
            recorder: The metrics recorder for recording request metrics.

        """
        self.app = app
        self._recorder = recorder
        self._start_time = time.monotonic()
        self._request_count = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process an ASGI request.

        Non-HTTP requests and excluded paths pass through without
        metrics collection.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.

        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]

        method: str = scope.get("method", "UNKNOWN")
        status_code = 0
        auth_failure_type: str | None = None

        # Read request_id from ContextVar (set by AuditMiddleware, the outermost middleware).
        request_id = request_id_context_var.get()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, auth_failure_type
            if message["type"] == "http.response.start":
                status_code = message["status"]
                filtered_headers, auth_failure_type = _process_response_headers(
                    list(message.get("headers", [])), request_id
                )
                message = {**message, "headers": filtered_headers}
            await send(message)

        if path in EXCLUDED_PATHS or path.startswith(EXCLUDED_PATH_PREFIXES):
            await self.app(scope, receive, send_wrapper)
            return

        start = time.perf_counter()

        interface = detect_interface(scope)
        interface_context_var.set(interface)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status_code = 500
            endpoint = _resolve_endpoint(scope, path)
            self._record_metrics(endpoint, method, status_code, start, interface, auth_failure_type)
            raise

        endpoint = _resolve_endpoint(scope, path)
        self._record_metrics(endpoint, method, status_code, start, interface, auth_failure_type)

    def _record_metrics(
        self,
        path: str,
        method: str,
        status_code: int,
        start: float,
        interface: str,
        auth_failure_type: str | None = None,
    ) -> None:
        """Record request duration, error, and auth failure metrics.

        Args:
            path: Request path.
            method: HTTP method.
            status_code: Response status code.
            start: ``time.perf_counter()`` at request start.
            interface: Originating interface (``"api"`` or ``"ui"``).
            auth_failure_type: Authentication failure type extracted from
                the ``X-Auth-Failure-Type`` response header, or ``None``
                for successful authentication.

        """
        duration_ms = (time.perf_counter() - start) * 1000
        status_str = str(status_code) if status_code else "0"

        labels = {
            "endpoint": path,
            "method": method,
            "status": status_str,
            "interface": interface,
        }

        component = ComponentLabel.SYSTEM_WIDE

        try:
            self._recorder.record(
                MetricType.REQUEST_DURATION,
                duration_ms,
                unit="ms",
                labels=labels,
            )
            self._recorder.record(
                MetricType.SYSTEM_E2E_LATENCY,
                duration_ms,
                unit="ms",
                component=component,
            )
            self._recorder.increment("requests")

            error_type = classify_error_type(status_code)
            if error_type is not None and auth_failure_type is None:
                self._recorder.record(
                    MetricType.ERROR,
                    1.0,
                    labels={
                        "error_type": error_type,
                        "endpoint": path,
                        "method": method,
                        "interface": interface,
                    },
                )
                self._recorder.increment("errors")

                summary = self._recorder.get_summary()
                if summary.total_requests > 0:
                    self._recorder.record(
                        MetricType.SYSTEM_ERROR_RATE,
                        summary.total_errors / summary.total_requests,
                        component=component,
                    )

            if auth_failure_type is not None:
                self._recorder.record(
                    MetricType.AUTH_FAILURE,
                    1.0,
                    labels={
                        "failure_type": auth_failure_type,
                        "interface": interface,
                    },
                )

            self._request_count += 1
            if error_type is not None or self._request_count % self._UPTIME_SAMPLE_INTERVAL == 0:
                self._recorder.record(
                    MetricType.SYSTEM_UPTIME,
                    time.monotonic() - self._start_time,
                    component=component,
                )

            if self._request_count % self._MEMORY_TRIM_INTERVAL == 0:
                gc.collect()
                release_memory_to_os()
        except Exception:  # noqa: BLE001
            logger.warning(
                "metrics_recording_failed",
                endpoint=path,
                exc_info=True,
            )
