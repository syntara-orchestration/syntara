"""Consumer service + process-wide registry, mirroring the Temporal WorkerRegistry.

Assembles the transport-neutral runtime from its injectable parts —
:class:`BrokerConnectionProvider` (where the broker comes from),
:class:`HandlerRegistry` (what to do per message), :class:`MessageFilter` (the
trigger gate) — builds the concrete adapter via :func:`build_consumer`, and wraps
it in an :class:`EventStreamConsumerService` the lifecycle can start and stop.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import structlog

from syntara.eventstreams.adapters import build_consumer
from syntara.eventstreams.core.pipeline import DispatchingEventHandler
from syntara.eventstreams.handlers import build_default_registry
from syntara.eventstreams.static_broker import StaticBrokerConnectionProvider

if TYPE_CHECKING:
    from syntara.eventstreams.core.connection import BrokerConnectionProvider
    from syntara.eventstreams.core.consumer import EventConsumer
    from syntara.eventstreams.core.envelope import Health
    from syntara.eventstreams.core.filter import MessageFilter
    from syntara.eventstreams.core.handler import WorkflowLauncher
    from syntara.eventstreams.core.registry import HandlerRegistry

logger = structlog.stdlib.get_logger(__name__)


class EventStreamConsumerService:
    """Owns a single running :class:`EventConsumer` and its lifecycle."""

    def __init__(self, consumer: EventConsumer) -> None:
        """Wrap the built consumer that this service will run and stop."""
        self._consumer = consumer

    async def run(self) -> None:
        """Run the consumer until it is stopped (blocks)."""
        await self._consumer.start()

    async def stop(self) -> None:
        """Request a graceful drain of the consumer."""
        await self._consumer.stop()

    async def health(self) -> Health:
        """Return the underlying consumer's liveness snapshot."""
        return await self._consumer.health()


class ConsumerRegistry:
    """Holds the process-wide consumer service, mirroring ``WorkerRegistry``."""

    def __init__(self) -> None:
        """Create an empty registry with no consumer service set."""
        self._service: EventStreamConsumerService | None = None

    def set(self, service: EventStreamConsumerService) -> None:
        """Register the process-wide consumer service."""
        self._service = service

    def get(self) -> EventStreamConsumerService | None:
        """Return the registered consumer service, if any."""
        return self._service

    def clear(self) -> None:
        """Forget the registered consumer service."""
        self._service = None


@lru_cache(maxsize=1)
def _get_consumer_registry() -> ConsumerRegistry:
    """Return the process-wide :class:`ConsumerRegistry` singleton."""
    return ConsumerRegistry()


async def start_consumer(
    *,
    provider: BrokerConnectionProvider | None = None,
    registry: HandlerRegistry | None = None,
    message_filter: MessageFilter | None = None,
    launcher: WorkflowLauncher | None = None,
) -> EventStreamConsumerService:
    """Build and start the consumer service, registering it as the singleton.

    Args:
        provider: where the broker connection + consumer config come from
            (defaults to the temporary hardcoded provider; swap for the
            Integration/Credential-backed provider later).
        registry: event_type -> handler map (defaults to a workflow-launch registry).
        message_filter: trigger gate (defaults to allow-all inside the pipeline).
        launcher: Temporal handoff seam used to build the default registry when
            ``registry`` is not supplied.

    """
    conn_provider = provider or StaticBrokerConnectionProvider()
    connection = await conn_provider.get_connection()
    config = await conn_provider.get_consumer_config()

    handler_registry = registry or build_default_registry(launcher)
    dispatcher = DispatchingEventHandler(
        handler_registry,
        message_filter=message_filter,
        broker_type=connection.broker_type.value,
        handler_timeout_seconds=config.handler_timeout_seconds,
    )

    consumer = build_consumer(connection, config, dispatcher)
    service = EventStreamConsumerService(consumer)
    _get_consumer_registry().set(service)
    logger.info(
        "eventstream_consumer_service_built",
        broker_type=connection.broker_type.value,
        topics=list(config.topics),
        group_id=config.group_id,
    )
    return service


async def stop_consumer() -> None:
    """Stop the singleton consumer service if one is running."""
    service = _get_consumer_registry().get()
    if service is not None:
        await service.stop()
        _get_consumer_registry().clear()
