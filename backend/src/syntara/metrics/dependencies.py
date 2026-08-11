"""FastAPI dependency providers for the metrics subsystem."""

from functools import lru_cache

from syntara.core.config.base import get_settings
from syntara.metrics.recorder import MetricsRecorder


@lru_cache(maxsize=1)
def get_metrics_recorder() -> MetricsRecorder:
    """Return the application-wide MetricsRecorder singleton.

    The recorder is lazily created on first access using values from
    :func:`~syntara.core.config.base.get_settings`.

    Use ``get_metrics_recorder.cache_clear()`` in tests to reset.
    """
    settings = get_settings()
    return MetricsRecorder(
        retention_seconds=settings.metrics_retention_seconds,
        max_records=settings.metrics_max_records,
        enabled=settings.metrics_enabled,
    )
