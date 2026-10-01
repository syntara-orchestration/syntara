"""Standalone event-stream consumer entrypoint.

Runs the transport-neutral consumer (Kafka today) as a separate process or
container, mirroring the Temporal worker entrypoint.

Usage:
    python -m syntara.eventstreams.consumer_entrypoint

The broker URL, topics, and auth token are hardcoded in
:mod:`syntara.eventstreams.static_broker` for now (temporary stand-in for the
Integration/Credential-backed provider), so no broker env vars are read here.

Environment Variables:
    APP_EVENTSTREAM_ENABLED: Enable the consumer worker (default: false)
    APP_FALLBACK_LOG_LEVEL: Logging level before runtime settings load (default: INFO)
"""

from __future__ import annotations

import asyncio

import structlog

from syntara.core.config.base import get_settings, validate_encryption_key_at_startup
from syntara.core.logging.lifecycle import start_loggers, stop_loggers
from syntara.eventstreams.consumer_lifecycle import run_consumer
from syntara.eventstreams.consumer_service import start_consumer

logger = structlog.stdlib.get_logger(__name__)

# Initialize logging subsystems (stdout + OTLP handlers)
start_loggers()


async def main() -> None:
    """Run the event-stream consumer worker."""
    validate_encryption_key_at_startup()

    settings = get_settings()
    if not settings.eventstream_enabled:
        logger.warning(
            "eventstream_consumer_disabled",
            detail="APP_EVENTSTREAM_ENABLED is false; not starting the consumer.",
        )
        return

    try:
        await run_consumer(start_consumer, worker_name="orchestrator-eventstream-consumer")
    finally:
        stop_loggers()


if __name__ == "__main__":
    asyncio.run(main())
