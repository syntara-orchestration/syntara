"""Standalone FastStream event-stream consumer entrypoint.

Runs the native FastStream consumer as a separate process or container.

Usage:
    python -m syntara.eventstreams.consumer_entrypoint

The broker URL, topics, and auth token are hardcoded in
:mod:`syntara.eventstreams.static_broker` for now, so no broker env vars are read.

Environment Variables:
    APP_EVENTSTREAM_ENABLED: Enable the consumer worker (default: false)
    APP_FALLBACK_LOG_LEVEL: Logging level before runtime settings load (default: INFO)
"""

from __future__ import annotations

import asyncio

import structlog

from syntara.core.config.base import get_settings, validate_encryption_key_at_startup
from syntara.core.logging.lifecycle import start_loggers, stop_loggers

logger = structlog.stdlib.get_logger(__name__)

# Initialize logging subsystems (stdout + OTLP handlers)
start_loggers()


async def main() -> None:
    """Run the FastStream event-stream consumer worker."""
    validate_encryption_key_at_startup()

    settings = get_settings()
    if not settings.eventstream_enabled:
        logger.warning(
            "eventstream_consumer_disabled",
            detail="APP_EVENTSTREAM_ENABLED is false; not starting the consumer.",
        )
        return

    # Imported lazily so the module (and its faststream/aiokafka import chain) is only
    # loaded when the consumer is actually enabled.
    from syntara.eventstreams.app import app  # noqa: PLC0415

    try:
        # FUTURE EDA RISK: app.run() is FastStream's own runner — it owns signal
        # handling and the graceful drain. This is NOT the shared ``run_consumer``
        # the Temporal worker uses, so the consumer's operational shape now diverges
        # from the worker's. A non-FastStream transport (Event Grid HTTP webhook)
        # could not be hosted by this call at all and would need a separate entrypoint.
        await app.run()
    finally:
        stop_loggers()


if __name__ == "__main__":
    asyncio.run(main())
