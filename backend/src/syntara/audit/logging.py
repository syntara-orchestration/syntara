"""Dedicated stdout logging for audit events.

Configures a Python logger ("syntara.audit") that writes audit events to stdout
unconditionally — independent of the application log level. This ensures audit
events are always visible in operational logs even when OTEL export is disabled
or unavailable.

The outbox worker (``syntara.audit.outbox.worker``) emits each audit event to this
logger before attempting OTEL export, guaranteeing at least a stdout record
exists for every processed event.

Usage:
    from syntara.audit.logging import AUDIT_LOGGER_NAME
    audit_logger = structlog.stdlib.get_logger(AUDIT_LOGGER_NAME)
    audit_logger.info("audit_event", **event_payload)
"""

import logging

import structlog

from syntara.core.logging.logging import build_nexus_formatter

# Logger name for audit event stdout output
AUDIT_LOGGER_NAME = "syntara.audit"

logger = structlog.stdlib.get_logger(__name__)


def configure_audit_logging() -> None:
    """Configure the dedicated audit stdout logger.

    Sets up the "syntara.audit" logger with a stdout handler at NOTSET level and
    propagate=False, ensuring audit events are always written to stdout regardless
    of the application's configured log level and without duplicating to the root
    logger.

    Called by core.logging.lifecycle during startup.
    """
    audit_otel_logger = logging.getLogger(AUDIT_LOGGER_NAME)

    # Create stdout handler for operational logs
    # This ensures audit events are ALWAYS visible in standard logs,
    # regardless of OTEL export configuration
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(build_nexus_formatter())
    stdout_handler.setLevel(logging.NOTSET)

    # Always attach stdout handler
    audit_otel_logger.addHandler(stdout_handler)

    # Set NOTSET level to ensure all audit events emit
    audit_otel_logger.setLevel(logging.NOTSET)

    # Prevent propagation to avoid duplicate logs in the root logger
    # (stdout_handler already writes to stdout, we don't need root logger to do it again)
    audit_otel_logger.propagate = False
