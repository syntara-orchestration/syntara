"""Integration tests for the metrics dependency provider."""

from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.recorder import MetricsRecorder


class TestGetMetricsRecorder:
    """Tests for the @lru_cache singleton dependency provider."""

    def setup_method(self) -> None:
        """Clear lru_cache before each test."""
        get_metrics_recorder.cache_clear()

    def teardown_method(self) -> None:
        """Clear lru_cache after each test."""
        get_metrics_recorder.cache_clear()

    def test_returns_recorder(self) -> None:
        """Dependency returns a MetricsRecorder instance."""
        recorder = get_metrics_recorder()
        assert isinstance(recorder, MetricsRecorder)

    def test_returns_same_instance(self) -> None:
        """Subsequent calls return the same cached singleton."""
        r1 = get_metrics_recorder()
        r2 = get_metrics_recorder()
        assert r1 is r2

    def test_cache_clear_creates_new_instance(self) -> None:
        """After cache_clear(), a new recorder is created."""
        r1 = get_metrics_recorder()
        get_metrics_recorder.cache_clear()
        r2 = get_metrics_recorder()
        assert r1 is not r2
