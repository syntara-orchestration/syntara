"""Broker adapters and the factory that selects one by :class:`BrokerType`.

This is the only place transport choice is resolved. ``core`` and the runtime
depend on the :class:`EventConsumer` interface, never on a concrete adapter, so
adding AWS/Azure is: implement an :class:`EventConsumer`, import it lazily here,
and add a branch. No other file changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from syntara.eventstreams.core.connection import BrokerConnection, BrokerType, ConsumerConfig
from syntara.eventstreams.core.exceptions import UnsupportedBrokerError

if TYPE_CHECKING:
    from syntara.eventstreams.core.consumer import EventConsumer
    from syntara.eventstreams.core.handler import EventHandler


def build_consumer(
    connection: BrokerConnection,
    config: ConsumerConfig,
    handler: EventHandler,
) -> EventConsumer:
    """Construct the :class:`EventConsumer` for ``connection.broker_type``.

    Raises:
        UnsupportedBrokerError: the broker family has no adapter yet.

    """
    if connection.broker_type is BrokerType.KAFKA:
        # Imported lazily so aiokafka is only required when a Kafka broker is used.
        from syntara.eventstreams.adapters.kafka import KafkaEventConsumer  # noqa: PLC0415

        return KafkaEventConsumer(connection, config, handler)

    msg = (
        f"no consumer adapter for broker type {connection.broker_type.value!r}; "
        "only 'kafka' is implemented (AWS/Azure are on the roadmap)"
    )
    raise UnsupportedBrokerError(msg)


__all__ = ["build_consumer"]
