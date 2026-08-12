"""OpenMetrics (Prometheus) scrape endpoint.

Provides the ``openmetrics_endpoint`` function registered as
``GET /metrics`` at the application root by ``main.py``.
"""

from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Response, status

from syntara.core.config.base import get_settings
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.recorder import MetricsRecorder

logger = structlog.stdlib.get_logger(__name__)


def openmetrics_endpoint(
    recorder: Annotated[MetricsRecorder, Depends(get_metrics_recorder)],
) -> Response:
    """OpenMetrics scrape endpoint.

    Returns metrics in the text-based OpenMetrics exposition format
    understood by Prometheus, Grafana Agent, and compatible scrapers.
    When metrics_openmetrics_enabled is False, returns 404.

    Args:
        recorder: Application metrics recorder (injected).

    Returns:
        Plain-text response in OpenMetrics format.

    """
    from prometheus_client import generate_latest  # noqa: PLC0415

    settings = get_settings()
    if not settings.metrics_openmetrics_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Openmetrics endpoint is disabled",
        )
    body = generate_latest(recorder.prometheus.registry)
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")
