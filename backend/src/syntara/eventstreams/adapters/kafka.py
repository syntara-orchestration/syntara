"""Kafka consumer adapter (the only module that imports aiokafka).

Translates a transport-neutral :class:`BrokerConnection` + :class:`ConsumerConfig`
into an ``AIOKafkaConsumer``, runs the receive loop, normalizes each record into an
:class:`EventEnvelope`, drives the shared handler, and acknowledges per the result:

- ``ACK``   -> commit the offset (strictly *after* the handler returns success).
- ``RETRY`` -> do NOT commit; rewind to the record's offset and back off so the
  same message is redelivered (at-least-once + back-pressure).

Concurrency model: one message at a time per consumer, so offset commits are
always correct. Parallelism is achieved the Kafka-native way — add partitions and
scale consumer-group replicas horizontally (ANSTRAT-1934 R3/P7R4).
"""

from __future__ import annotations

import asyncio
import ssl
from typing import TYPE_CHECKING

import structlog
from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.errors import KafkaConnectionError, KafkaError

from syntara.core.tls.kafka import build_kafka_ssl_context
from syntara.eventstreams.core.connection import (
    BrokerConnection,
    ConsumerConfig,
    SecurityProtocol,
)
from syntara.eventstreams.core.consumer import EventConsumer
from syntara.eventstreams.core.envelope import EventEnvelope, HandlerResult, Health
from syntara.eventstreams.core.exceptions import ConsumerConnectionError
from syntara.eventstreams.core.metrics import ASSIGNED_PARTITIONS, MESSAGES_RECEIVED

if TYPE_CHECKING:
    from aiokafka.structs import ConsumerRecord

    from syntara.eventstreams.core.handler import EventHandler

logger = structlog.stdlib.get_logger(__name__)

_EVENT_TYPE_HEADER = "event_type"


class KafkaEventConsumer(EventConsumer):
    """An :class:`EventConsumer` backed by aiokafka."""

    def __init__(
        self,
        connection: BrokerConnection,
        config: ConsumerConfig,
        handler: EventHandler,
    ) -> None:
        """Store the connection, consumer config, and handler (no I/O yet)."""
        self._connection = connection
        self._config = config
        self._handler = handler
        self._consumer: AIOKafkaConsumer | None = None
        self._stop = asyncio.Event()
        self._running = False

    async def start(self) -> None:
        """Connect, then run the receive loop until :meth:`stop` is requested."""
        self._consumer = self._build_consumer()
        try:
            await self._consumer.start()
        except (KafkaConnectionError, KafkaError) as exc:
            msg = f"failed to connect Kafka consumer to {self._connection.bootstrap_servers}: {exc}"
            raise ConsumerConnectionError(msg) from exc

        self._running = True
        logger.info(
            "kafka_consumer_started",
            topics=list(self._config.topics),
            group_id=self._config.group_id,
            bootstrap_servers=self._connection.bootstrap_servers,
        )
        try:
            await self._run_loop()
        finally:
            self._running = False
            await self._consumer.stop()  # leaves the group cleanly, triggers a rebalance
            logger.info("kafka_consumer_stopped", group_id=self._config.group_id)

    async def stop(self) -> None:
        """Signal the receive loop to drain the in-flight message and exit."""
        logger.info("kafka_consumer_stop_requested", group_id=self._config.group_id)
        self._stop.set()

    async def health(self) -> Health:
        """Return a liveness snapshot including the assigned-partition count."""
        if not self._running or self._consumer is None:
            return Health(healthy=False, detail="consumer not running")
        assigned = self._consumer.assignment()
        return Health(healthy=True, assigned_partitions=len(assigned))

    async def _run_loop(self) -> None:
        assert self._consumer is not None  # noqa: S101 — guaranteed by start()
        consumer = self._consumer
        broker = self._connection.broker_type.value

        while not self._stop.is_set():
            # Short timeout so the stop event is observed promptly for graceful drain.
            batch = await consumer.getmany(timeout_ms=1000, max_records=1)
            self._update_partition_gauge()
            for records in batch.values():
                for record in records:
                    if self._stop.is_set():
                        return
                    MESSAGES_RECEIVED.labels(broker_type=broker, source=record.topic).inc()
                    result = await self._handler.handle(self._to_envelope(record))
                    if result is HandlerResult.ACK:
                        await consumer.commit()
                    else:
                        await self._rewind(record)

    async def _rewind(self, record: ConsumerRecord) -> None:
        """Rewind to a record's offset (no commit) and back off, forcing redelivery."""
        assert self._consumer is not None  # noqa: S101
        tp = TopicPartition(record.topic, record.partition)
        self._consumer.seek(tp, record.offset)
        await asyncio.sleep(self._config.retry_backoff_seconds)

    def _update_partition_gauge(self) -> None:
        assert self._consumer is not None  # noqa: S101
        ASSIGNED_PARTITIONS.labels(
            broker_type=self._connection.broker_type.value,
            group_id=self._config.group_id,
        ).set(len(self._consumer.assignment()))

    @staticmethod
    def _to_envelope(record: ConsumerRecord) -> EventEnvelope:
        headers = {k: (v.decode() if isinstance(v, bytes) else str(v)) for k, v in (record.headers or [])}
        key = record.key.decode() if isinstance(record.key, bytes) else record.key
        return EventEnvelope(
            message_id=f"{record.topic}-{record.partition}-{record.offset}",
            source=record.topic,
            body=record.value if isinstance(record.value, bytes) else bytes(record.value or b""),
            headers=headers,
            key=key,
            partition_key=key,
            event_type=headers.get(_EVENT_TYPE_HEADER),
            raw=record,
        )

    def _build_consumer(self) -> AIOKafkaConsumer:
        conn = self._connection
        use_tls = conn.security_protocol in (SecurityProtocol.SSL, SecurityProtocol.SASL_SSL)
        sasl = conn.sasl
        return AIOKafkaConsumer(
            *self._config.topics,
            bootstrap_servers=conn.bootstrap_servers,
            group_id=self._config.group_id,
            enable_auto_commit=False,  # manual commit AFTER a successful handoff
            auto_offset_reset=self._config.auto_offset_reset,
            security_protocol=conn.security_protocol.value,
            ssl_context=self._ssl_context() if use_tls else None,
            sasl_mechanism=sasl.mechanism.value if sasl else "PLAIN",
            sasl_plain_username=sasl.username if sasl else None,
            sasl_plain_password=(sasl.password.get_secret_value() if sasl and sasl.password is not None else None),
        )

    def _ssl_context(self) -> ssl.SSLContext:
        """SSL context for TLS/SASL_SSL: custom CA/mTLS if given, else system trust.

        A managed broker deployed elsewhere typically presents a publicly-trusted
        certificate, so when no :class:`TlsMaterial` is supplied we fall back to
        the system trust store rather than refusing to connect.
        """
        return build_kafka_ssl_context(self._connection.tls) or ssl.create_default_context()
