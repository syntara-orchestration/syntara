"""Compose Kafka + AWS + Azure into one FastStream app.

``FastStream(*brokers)`` accepts multiple brokers (verified), so a single app object
CAN own all three. But note what the composition below actually shows:

- The wiring is per-broker and near-identical (build broker -> add middleware ->
  include router -> append). It cannot be looped cleanly because each build_* returns
  a different broker type with a different, non-substitutable router.
- AWS and Azure have no first-party broker, so in practice this "multi-cloud" app
  degrades to Kafka-only at runtime — the other two log a BrokerNotAvailableError and
  are skipped. That silent degradation to one working transport is the honest state
  of native FastStream multi-cloud today.
"""

from __future__ import annotations

import structlog
from faststream import FastStream

from syntara.core.config.base import get_settings
from syntara.eventstreams.multicloud.brokers import BrokerNotAvailableError
from syntara.eventstreams.multicloud.brokers.aws_router import build_aws_broker, build_aws_router
from syntara.eventstreams.multicloud.brokers.azure_router import build_azure_broker, build_azure_router
from syntara.eventstreams.multicloud.brokers.kafka_router import build_kafka_broker, build_kafka_router
from syntara.eventstreams.multicloud.middleware import observability_for

logger = structlog.stdlib.get_logger(__name__)


def build_multicloud_app() -> FastStream:
    """Build a single FastStream app fronting every available broker."""
    brokers = []

    # --- Kafka (first-party, works) ---------------------------------------- #
    # DUPLICACY RISK [BROKER-SPECIFIC]: this 3-line wiring block is repeated verbatim
    # per transport and cannot be a loop — build_* returns different broker types and
    # observability_for() needs a per-transport label.
    kafka_broker = build_kafka_broker()
    kafka_broker.add_middleware(observability_for("kafka"))
    kafka_broker.include_router(build_kafka_router())
    brokers.append(kafka_broker)

    # --- AWS SQS/SNS (no first-party broker -> skipped at runtime) ---------- #
    try:
        aws_broker = build_aws_broker()
        aws_broker.add_middleware(observability_for("aws"))
        aws_broker.include_router(build_aws_router())
        brokers.append(aws_broker)
    except BrokerNotAvailableError as exc:
        logger.warning("multicloud_aws_skipped", detail=str(exc))

    # --- Azure Service Bus (no first-party broker -> skipped at runtime) ---- #
    try:
        azure_broker = build_azure_broker()
        azure_broker.add_middleware(observability_for("azure"))
        azure_broker.include_router(build_azure_router())
        brokers.append(azure_broker)
    except BrokerNotAvailableError as exc:
        logger.warning("multicloud_azure_skipped", detail=str(exc))

    app = FastStream(*brokers)

    @app.on_startup
    async def _on_startup() -> None:
        _start_metrics_server()
        logger.info("multicloud_consumer_started", active_brokers=[type(b).__name__ for b in brokers])

    return app


def _start_metrics_server() -> None:
    """Expose Prometheus metrics on the shared worker port (bind failure ignored)."""
    import prometheus_client

    port = get_settings().metrics_worker_port
    try:
        prometheus_client.start_http_server(port)
        logger.info("Consumer metrics server started", port=port)
    except OSError as exc:
        logger.warning("Consumer metrics server could not bind — skipping", port=port, error=str(exc))


app = build_multicloud_app()
