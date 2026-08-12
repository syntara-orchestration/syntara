"""Unit tests for core logging lifecycle management.

Tests cover:
- Logger initialization and startup (root logger)
- Logger shutdown and flushing
- Thread-safe state transitions
- Idempotent start/stop operations
- Logger restart after shutdown
- Handler cleanup
"""

import logging
import threading
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from syntara.core.logging.lifecycle import OtelLoggingState, start_loggers, stop_loggers

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture(autouse=True)
def _reset_logging_state() -> Generator[None, None, None]:
    """Reset logging state and handlers between tests to ensure isolation."""
    import syntara.core.logging.lifecycle as lifecycle_module
    from syntara.audit.logging import AUDIT_LOGGER_NAME

    # Reset state before test
    with lifecycle_module._logging_state_lock:
        lifecycle_module._logging_state = OtelLoggingState.UNCONFIGURED

    # Clean up handlers
    root_logger = logging.getLogger()
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    for handler in audit_logger.handlers[:]:
        audit_logger.removeHandler(handler)
    audit_logger.disabled = False

    yield

    # Clean up after test
    with lifecycle_module._logging_state_lock:
        lifecycle_module._logging_state = OtelLoggingState.UNCONFIGURED

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    for handler in audit_logger.handlers[:]:
        audit_logger.removeHandler(handler)
    audit_logger.disabled = False


# ------------------------------------------------------------------ #
# Helper Functions
# ------------------------------------------------------------------ #


def _reset_lifecycle_state() -> None:
    """Reset module-level lifecycle state to UNCONFIGURED (for test isolation)."""
    import syntara.core.logging.lifecycle as lifecycle_module

    with lifecycle_module._logging_state_lock:
        lifecycle_module._logging_state = OtelLoggingState.UNCONFIGURED


# ------------------------------------------------------------------ #
# Start Tests
# ------------------------------------------------------------------ #


class TestStartLoggers:
    """Test start_loggers function."""

    @patch("syntara.core.logging.lifecycle.configure_audit_logging")
    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_configures_app_and_audit_logging(
        self,
        mock_configure_app: MagicMock,
        mock_configure_audit: MagicMock,
    ) -> None:
        """Test that start_loggers configures both application and audit logging."""
        start_loggers()

        mock_configure_app.assert_called_once()
        mock_configure_audit.assert_called_once()

    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_sets_configured_state(self, mock_configure_app: MagicMock) -> None:
        """Test that start_loggers transitions state to CONFIGURED."""
        start_loggers()

        import syntara.core.logging.lifecycle as lifecycle_module

        assert lifecycle_module._logging_state == OtelLoggingState.CONFIGURED

    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_idempotent_when_already_configured(self, mock_configure_app: MagicMock) -> None:
        """Test that calling start_loggers when already configured is a no-op."""
        start_loggers()
        assert mock_configure_app.call_count == 1

        start_loggers()
        assert mock_configure_app.call_count == 1

    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_logs_already_configured(self, mock_configure_app: MagicMock) -> None:
        """Test that calling start_loggers when configured logs a debug message."""
        with patch("syntara.core.logging.lifecycle.logger") as mock_logger:
            start_loggers()
            start_loggers()

            mock_logger.debug.assert_called_with("logging.already_configured", state=OtelLoggingState.CONFIGURED)

    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_thread_safe_concurrent_calls(self, mock_configure_app: MagicMock) -> None:
        """Test that concurrent start_loggers calls are thread-safe (only one configures)."""
        barrier = threading.Barrier(2)

        def concurrent_start() -> None:
            barrier.wait()
            start_loggers()

        thread1 = threading.Thread(target=concurrent_start)
        thread2 = threading.Thread(target=concurrent_start)

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        assert mock_configure_app.call_count == 1

    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_logs_success_message(self, mock_configure_app: MagicMock) -> None:
        """Test that start_loggers logs a success message."""
        with patch("syntara.core.logging.lifecycle.logger") as mock_logger:
            start_loggers()

            mock_logger.info.assert_called_with("logging.configured")


# ------------------------------------------------------------------ #
# Stop Tests
# ------------------------------------------------------------------ #


class TestStopLoggers:
    """Test stop_loggers function."""

    @patch("syntara.core.logging.lifecycle.flush_otel_handler")
    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_flushes_root_logger(
        self,
        mock_configure_app: MagicMock,
        mock_flush: MagicMock,
    ) -> None:
        """Test that stop_loggers flushes the root logger."""
        start_loggers()
        stop_loggers()

        mock_flush.assert_called_once()

        root_logger = logging.getLogger()
        mock_flush.assert_called_with(root_logger)

    @patch("syntara.core.logging.lifecycle.flush_otel_handler")
    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_removes_root_logger_handlers(
        self,
        mock_configure_app: MagicMock,
        mock_flush: MagicMock,
    ) -> None:
        """Test that stop_loggers removes all root logger handlers."""
        root_logger = logging.getLogger()
        test_handler = logging.StreamHandler()
        root_logger.addHandler(test_handler)

        start_loggers()
        initial_count = len(root_logger.handlers)
        assert initial_count > 0

        stop_loggers()

        assert len(root_logger.handlers) == 0

    @patch("syntara.core.logging.lifecycle.flush_otel_handler")
    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_sets_unconfigured_state(
        self,
        mock_configure_app: MagicMock,
        mock_flush: MagicMock,
    ) -> None:
        """Test that stop_loggers transitions state to UNCONFIGURED."""
        start_loggers()
        stop_loggers()

        import syntara.core.logging.lifecycle as lifecycle_module

        assert lifecycle_module._logging_state == OtelLoggingState.UNCONFIGURED

    @patch("syntara.core.logging.lifecycle.flush_otel_handler")
    def test_idempotent_when_already_stopped(self, mock_flush: MagicMock) -> None:
        """Test that calling stop_loggers when already stopped is a no-op."""
        stop_loggers()

        mock_flush.assert_not_called()

    @patch("syntara.core.logging.lifecycle.flush_otel_handler")
    def test_logs_already_stopped(self, mock_flush: MagicMock) -> None:
        """Test that calling stop_loggers when stopped logs a debug message."""
        with patch("syntara.core.logging.lifecycle.logger") as mock_logger:
            stop_loggers()

            mock_logger.debug.assert_called_with(
                "logging.flush_skipped_not_configured", state=OtelLoggingState.UNCONFIGURED
            )

    @patch("syntara.core.logging.lifecycle.flush_otel_handler")
    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_logs_success_message(
        self,
        mock_configure_app: MagicMock,
        mock_flush: MagicMock,
    ) -> None:
        """Test that stop_loggers logs shutdown messages."""
        with patch("syntara.core.logging.lifecycle.logger") as mock_logger:
            start_loggers()
            stop_loggers()

            info_calls = mock_logger.info.call_args_list
            stop_messages = [call[0][0] for call in info_calls[1:]]
            assert "logging.flushed_and_stopped" in stop_messages
            assert "logging.removing_root_handlers" in stop_messages
            assert "logging.removing_audit_handlers" in stop_messages

    @patch("syntara.core.logging.lifecycle.flush_otel_handler")
    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_flush_before_handler_removal(
        self,
        mock_configure_app: MagicMock,
        mock_flush: MagicMock,
    ) -> None:
        """Test that handlers are flushed before being removed."""
        call_order: list[str] = []

        def track_flush(logger: logging.Logger) -> None:
            call_order.append(f"flush_{logger.name or 'root'}")

        mock_flush.side_effect = track_flush

        root_logger = logging.getLogger()

        start_loggers()

        original_remove_handler = root_logger.removeHandler

        def track_remove(handler: logging.Handler) -> None:
            call_order.append("remove_root")
            original_remove_handler(handler)

        root_logger.removeHandler = track_remove  # type: ignore[assignment,method-assign]

        stop_loggers()

        flush_root_index = next(i for i, v in enumerate(call_order) if v == "flush_root")
        first_remove_index = next((i for i, v in enumerate(call_order) if v.startswith("remove_")), len(call_order))

        assert flush_root_index < first_remove_index


# ------------------------------------------------------------------ #
# Restart Tests
# ------------------------------------------------------------------ #


class TestRestartLoggers:
    """Test restarting the logging system after shutdown."""

    @patch("syntara.core.logging.lifecycle.flush_otel_handler")
    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_can_restart_after_stop(
        self,
        mock_configure_app: MagicMock,
        mock_flush: MagicMock,
    ) -> None:
        """Test that loggers can be restarted after being stopped."""
        start_loggers()
        assert mock_configure_app.call_count == 1

        stop_loggers()
        assert mock_flush.call_count == 1

        start_loggers()
        assert mock_configure_app.call_count == 2

    @patch("syntara.core.logging.lifecycle.flush_otel_handler")
    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_multiple_start_stop_cycles(
        self,
        mock_configure_app: MagicMock,
        mock_flush: MagicMock,
    ) -> None:
        """Test multiple start/stop cycles work correctly."""
        for i in range(3):
            start_loggers()
            assert mock_configure_app.call_count == i + 1

            stop_loggers()
            assert mock_flush.call_count == i + 1

            import syntara.core.logging.lifecycle as lifecycle_module

            assert lifecycle_module._logging_state == OtelLoggingState.UNCONFIGURED


# ------------------------------------------------------------------ #
# Thread Safety Tests
# ------------------------------------------------------------------ #


class TestThreadSafety:
    """Test thread safety of lifecycle operations."""

    @patch("syntara.core.logging.lifecycle.flush_otel_handler")
    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_state_transitions_are_atomic(
        self,
        mock_configure_app: MagicMock,
        mock_flush: MagicMock,
    ) -> None:
        """Test that state transitions under lock prevent race conditions."""
        threads = [threading.Thread(target=start_loggers) for _ in range(10)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        assert mock_configure_app.call_count == 1

        import syntara.core.logging.lifecycle as lifecycle_module

        assert lifecycle_module._logging_state == OtelLoggingState.CONFIGURED

    @patch("syntara.core.logging.lifecycle.flush_otel_handler")
    @patch("syntara.core.logging.lifecycle.configure_app_logging")
    def test_stop_waits_for_lock(
        self,
        mock_configure_app: MagicMock,
        mock_flush: MagicMock,
    ) -> None:
        """Test that stop waits for lock even if start holds it."""
        start_loggers()
        stop_loggers()

        import syntara.core.logging.lifecycle as lifecycle_module

        assert lifecycle_module._logging_state == OtelLoggingState.UNCONFIGURED
