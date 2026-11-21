"""Shared OpenTelemetry logging handler creation and lifecycle management.

This module provides factory functions for creating OTLP (OpenTelemetry Protocol)
log handlers that can be attached to any Python logger. It centralizes OTLP
configuration logic to avoid duplication between audit and general application logging.

Functions:
    create_otel_handler: Factory for creating OTLP handlers with authentication
    flush_otel_handler: Flush pending log records from OTLP handlers
"""

import logging
import os

import structlog
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from syntara.core.config.base import get_settings

logger = structlog.stdlib.get_logger(__name__)


def create_otel_handler() -> logging.Handler | None:
    """Create an OTLP logging handler for the specified logger.

    Creates a LoggingHandler that exports log records to an OTLP collector via HTTP.
    Supports authentication via API key (bearer token) or mTLS (client certificates).

    Returns:
        LoggingHandler configured with OTLP exporter, or None if OTLP is disabled

    """
    settings = get_settings()
    if not settings.otel_enabled:
        return None

    # Create OTLP exporter with authentication
    otlp_exporter = create_otlp_exporter()

    # Create logger provider with resource/service identification
    logger_provider = _create_logger_provider(otlp_exporter)

    # Create OpenTelemetry logging handler
    return LoggingHandler(
        level=logging.NOTSET,
        logger_provider=logger_provider,
    )


def flush_otel_handler(target_logger: logging.Logger) -> None:
    """Flush any OTLP handlers attached to the given logger.

    Iterates through the logger's handlers and flushes any that have a logger_provider
    attribute (i.e., OTLP LoggingHandler instances). This ensures pending log records
    in the BatchLogRecordProcessor are exported before shutdown.

    Best-effort: catches exceptions per handler, logs warnings, continues to next handler.

    Args:
        target_logger: Logger whose OTLP handlers should be flushed

    """
    for handler in target_logger.handlers:
        if not hasattr(handler, "logger_provider"):
            continue

        try:
            handler.flush()
            handler.logger_provider.force_flush()
            logger.info(
                "otel.handler.flushed",
                logger_name=target_logger.name,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "otel.handler.flush_failed",
                logger_name=target_logger.name,
                exc_info=True,
            )


def create_otlp_exporter() -> OTLPLogExporter:
    """Create OTLPLogExporter with authentication.

    Supports:
    - API key authentication via Authorization: Bearer <token> header
    - mTLS authentication via client certificate/key files

    Returns:
        OTLPLogExporter configured with endpoint and authentication

    """
    settings = get_settings()
    # Build authentication headers if API key is configured
    headers = None
    if settings.otel_api_key:
        headers = {
            settings.otel_auth_header_name: f"Bearer {settings.otel_api_key.get_secret_value()}",
        }

    # Determine if mTLS is configured
    has_mtls = settings.otel_client_cert_file and settings.otel_client_key_file

    # Warn if no authentication is configured
    if not settings.otel_api_key and not has_mtls:
        logger.warning(
            "otel.handler.no_authentication",
            endpoint=settings.otel_endpoint,
            message="OTLP endpoint configured without authentication (no API key or mTLS)",
        )

    # Create OTLP exporter with authentication
    # HTTP transport uses URL scheme for security (http:// vs https://)
    return OTLPLogExporter(
        endpoint=settings.otel_endpoint,
        headers=headers,
        certificate_file=settings.otel_ca_cert_file,
        client_certificate_file=settings.otel_client_cert_file,
        client_key_file=settings.otel_client_key_file,
    )


def create_otel_resource() -> Resource:
    """Create OTEL Resource with service identification.

    Returns:
        Resource with service.name and service.instance.id attributes

    """
    settings = get_settings()
    return Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.instance.id": os.uname().nodename,
        }
    )


def _create_logger_provider(otlp_exporter: OTLPLogExporter) -> LoggerProvider:
    """Create LoggerProvider with resource identification (private helper).

    Sets service.name and service.instance.id for identifying logs in the collector.
    Attaches a BatchLogRecordProcessor with the given OTLP exporter.

    Args:
        otlp_exporter: OTLPLogExporter instance

    Returns:
        LoggerProvider configured with resource and batch processor

    """
    resource = create_otel_resource()

    # Create logger provider
    logger_provider = LoggerProvider(resource=resource)

    # Add batch processor with OTLP exporter
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_exporter))

    return logger_provider
