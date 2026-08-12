"""Centralized logging lifecycle orchestration.

This module coordinates the setup and teardown of the application logging
subsystem (root logger with stdout + OTLP export).

Audit event export to OTEL is handled directly by the outbox worker via
``OTLPLogExporter.export()`` — not through the logging pipeline.

It ensures thread-safe, idempotent initialization and clean shutdown with
proper flushing of pending OTLP log records.

Usage:
    # At application startup (e.g., in main.py lifespan):
    start_loggers()

    # At application shutdown:
    stop_loggers()
"""

import logging
import threading
from enum import StrEnum

import structlog

from syntara.audit.logging import AUDIT_LOGGER_NAME, configure_audit_logging
from syntara.core.logging.logging import configure_app_logging
from syntara.core.logging.otel_handlers import flush_otel_handler

logger = structlog.stdlib.get_logger(__name__)


class OtelLoggingState(StrEnum):
    """OTEL logging lifecycle states."""

    UNCONFIGURED = "unconfigured"
    CONFIGURED = "configured"


# Thread lock to ensure thread-safe state transitions
_logging_state_lock = threading.Lock()
_logging_state = OtelLoggingState.UNCONFIGURED


def start_loggers() -> None:
    """Initialize and start all logging subsystems.

    Configures the root logger with stdout and OTLP handlers.

    Thread-safe and idempotent - safe to call multiple times.
    Can be called after stop_loggers() to restart logging.
    """
    global _logging_state  # noqa: PLW0603

    with _logging_state_lock:
        if _logging_state == OtelLoggingState.CONFIGURED:
            logger.debug(
                "logging.already_configured",
                state=_logging_state,
            )
            return

        # Configure root logger (stdout + OTLP)
        configure_app_logging()

        # Configure audit logger (stdout, NOTSET level, no propagation)
        configure_audit_logging()

        _logging_state = OtelLoggingState.CONFIGURED
        logger.info("logging.configured")


def stop_loggers() -> None:
    """Flush and stop the application logging subsystem.

    Flushes pending OTLP log records for the root logger,
    then removes all handlers to allow clean restart.

    Thread-safe and idempotent - safe to call multiple times.
    """
    global _logging_state  # noqa: PLW0603

    with _logging_state_lock:
        if _logging_state == OtelLoggingState.UNCONFIGURED:
            logger.debug(
                "logging.flush_skipped_not_configured",
                state=_logging_state,
            )
            return

        # Flush root logger OTLP handlers
        root_logger = logging.getLogger()
        flush_otel_handler(root_logger)
        logger.info("logging.flushed_and_stopped")

        # Remove handlers to allow clean restart
        logger.info("logging.removing_root_handlers")
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        logger.info("logging.removing_audit_handlers")
        audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
        for handler in audit_logger.handlers[:]:
            audit_logger.removeHandler(handler)

        _logging_state = OtelLoggingState.UNCONFIGURED
