"""The native FastStream app: broker + subscriber callback + lifecycle hooks.

This single module is where the aiokafka POC's ``core.pipeline.DispatchingEventHandler``,
``core.serialization``, ``core.filter``, ``adapters.kafka.KafkaEventConsumer``, and
``consumer_lifecycle`` all collapse into FastStream-native code:

    @broker.subscriber(...) callback  ==  deserialize -> filter -> dispatch -> classify
    KafkaMessage.ack() / .nack()      ==  the process-then-commit / redelivery seam
    @app.on_startup / @app.on_shutdown==  the process lifecycle

Because it is all expressed against FastStream's Kafka primitives, it is the primary
site of ``# FUTURE EDA RISK:`` debt — see the comments inline.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Literal, cast

import structlog
from faststream import AckPolicy, FastStream

# Runtime import (NOT TYPE_CHECKING): FastStream resolves the subscriber's annotations
# at runtime via get_type_hints for dependency injection, so KafkaMessage must be a
# real import even though it is only used in annotations.
from faststream.kafka import KafkaMessage  # noqa: TC002

from syntara.core.config.base import get_settings
from syntara.eventstreams.handlers import (
    PermanentHandoffError,
    TransientHandoffError,
    resolve_handler,
)
from syntara.eventstreams.metrics import (
    ASSIGNED_PARTITIONS,
    HANDOFF_LATENCY,
    MESSAGES_HANDLED,
    MESSAGES_RECEIVED,
    REDELIVERIES,
)
from syntara.eventstreams.static_broker import (
    AUTO_OFFSET_RESET,
    GROUP_ID,
    HANDLER_TIMEOUT_SECONDS,
    RETRY_BACKOFF_SECONDS,
    TOPICS,
    build_broker,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from aiokafka import ConsumerRecord

logger = structlog.stdlib.get_logger(__name__)

_BROKER_TYPE = "kafka"  # constant: native FastStream has no broker abstraction to vary this
_EVENT_TYPE_HEADER = "event_type"

# Transient failures that mean "withhold commit -> redeliver". Mirrors the AO
# wrapper's ``_TRANSIENT_EXCEPTIONS`` — but here it lives inside the Kafka callback
# instead of a shared, broker-neutral pipeline.
_TRANSIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    TransientHandoffError,
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
)

broker = build_broker()
app = FastStream(broker)


# FUTURE EDA RISK: the entire subscriber below is bound to ``broker`` (a KafkaBroker)
# and to Kafka message shape (raw_message = ConsumerRecord, offset commit = ack).
# A second transport cannot reuse this callback — it needs its own
# ``@sqs_broker.subscriber`` / ``@servicebus_broker.subscriber`` with the SAME
# deserialize->filter->dispatch->classify body copy-pasted and its ack/nack calls
# swapped for that transport's semantics. In the AO wrapper this body existed ONCE
# (broker-neutral pipeline) and each transport only translated ack/nack. Removing
# the wrapper trades that single implementation for per-broker duplication.
@broker.subscriber(
    *TOPICS,
    group_id=GROUP_ID,
    auto_offset_reset=cast("Literal['latest', 'earliest', 'none']", AUTO_OFFSET_RESET),
    # One record at a time + manual ack == process-then-commit, at-least-once.
    max_records=1,
    ack_policy=AckPolicy.MANUAL,
)
async def consume(msg: KafkaMessage) -> None:
    """Handle one Kafka message: deserialize -> filter -> dispatch -> ack/nack."""
    record = _single_record(msg)
    source = str(record.topic)
    # Kafka-coordinate identity. FUTURE EDA RISK: this format is Kafka-only and is the
    # basis for Temporal's deterministic dedup id (see handlers._launch_workflow_stub).
    message_id = f"{record.topic}-{record.partition}-{record.offset}"

    MESSAGES_RECEIVED.labels(broker_type=_BROKER_TYPE, source=source).inc()
    _update_partition_gauge(msg)

    started = time.monotonic()

    # 1. Deserialize. An undecodable payload is a no-trigger decision, not a failure.
    try:
        payload = _deserialize(record.value)
    except _DeserializeError as exc:
        logger.warning("eventstream_deserialize_failed", message_id=message_id, source=source, error=str(exc))
        await _ack(msg, source, "ack_no_trigger")
        return

    headers = _decode_headers(record.headers)
    event_type = headers.get(_EVENT_TYPE_HEADER)

    # 2. Filter. No match -> no-trigger decision.
    if not _matches(payload, headers):
        logger.debug("eventstream_filtered_out", message_id=message_id, source=source)
        await _ack(msg, source, "ack_no_trigger")
        return

    # 3. Dispatch by event_type. Unknown type with no default -> no-trigger decision.
    handler = resolve_handler(event_type)
    if handler is None:
        logger.warning("eventstream_no_handler", message_id=message_id, source=source, event_type=event_type)
        await _ack(msg, source, "ack_no_trigger")
        return

    # 4. Handoff. Only a transient failure withholds the commit.
    try:
        await asyncio.wait_for(
            handler(payload, message_id=message_id, source=source, event_type=event_type, headers=headers),
            timeout=HANDLER_TIMEOUT_SECONDS,
        )
    except _TRANSIENT_EXCEPTIONS as exc:
        logger.warning("eventstream_handoff_transient_failure", message_id=message_id, source=source, error=str(exc))
        REDELIVERIES.labels(broker_type=_BROKER_TYPE, source=source).inc()
        MESSAGES_HANDLED.labels(broker_type=_BROKER_TYPE, source=source, outcome="retry").inc()
        HANDOFF_LATENCY.labels(broker_type=_BROKER_TYPE, source=source).observe(time.monotonic() - started)
        # nack == seek back to this offset (no commit) so the broker redelivers.
        await msg.nack()
        await asyncio.sleep(RETRY_BACKOFF_SECONDS)  # back-pressure
        return
    except PermanentHandoffError as exc:
        # Non-retriable: ACK anyway so the partition is never blocked (no DLQ).
        logger.error("eventstream_handoff_permanent_failure", message_id=message_id, source=source, error=str(exc))  # noqa: TRY400
        HANDOFF_LATENCY.labels(broker_type=_BROKER_TYPE, source=source).observe(time.monotonic() - started)
        await _ack(msg, source, "error")
        return
    except Exception:
        # Unexpected/unclassified error: treat as permanent to avoid a crash-loop.
        logger.exception("eventstream_handoff_unexpected_error", message_id=message_id, source=source)
        HANDOFF_LATENCY.labels(broker_type=_BROKER_TYPE, source=source).observe(time.monotonic() - started)
        await _ack(msg, source, "error")
        return

    HANDOFF_LATENCY.labels(broker_type=_BROKER_TYPE, source=source).observe(time.monotonic() - started)
    await _ack(msg, source, "ack_triggered")


# FUTURE EDA RISK: FastStream owns the process lifecycle via app.run() and these
# hooks. In the AO wrapper, lifecycle lived in a shared ``run_consumer`` that matched
# the Temporal worker exactly (same metrics port, signal handling, graceful drain).
# Here the metrics server is bolted onto a FastStream startup hook; a second transport
# running under the same app would share these hooks, but a transport that is NOT a
# FastStream broker (e.g. an Event Grid HTTP webhook) cannot run under app.run() at
# all and needs a separate host — re-fragmenting the "one operational shape" the
# wrapper provided.
@app.on_startup
async def _on_startup() -> None:
    """Expose Prometheus metrics and log readiness."""
    _start_metrics_server()
    logger.info("faststream_eventstream_consumer_started", topics=list(TOPICS), group_id=GROUP_ID)


@app.on_shutdown
async def _on_shutdown() -> None:
    """Log a clean shutdown (FastStream drains the subscriber before this runs)."""
    logger.info("faststream_eventstream_consumer_stopped", group_id=GROUP_ID)


# --------------------------------------------------------------------------- #
# Helpers — all Kafka-shaped, folded next to the callback.                     #
# --------------------------------------------------------------------------- #


class _DeserializeError(Exception):
    """Payload could not be decoded — treated as a no-trigger decision."""


def _deserialize(body: bytes | None) -> object:
    """Decode a UTF-8 JSON body, or ``None`` for an empty body."""
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = f"payload is not valid JSON: {exc}"
        raise _DeserializeError(msg) from exc


def _matches(payload: object, headers: Mapping[str, str]) -> bool:  # noqa: ARG001
    """Trigger gate. POC default: allow every message.

    # FUTURE EDA RISK: the richer expression language (JMESPath/CEL/Rego, ANSTRAT-1934
    # P4) would plug in here, inside the Kafka callback. In the AO wrapper it was a
    # broker-neutral ``MessageFilter`` reused by every transport; here each transport's
    # callback must call its own filter, so the filter either duplicates or has to be
    # lifted back into a shared module (rebuilding the wrapper seam).
    """
    return True


def _decode_headers(raw_headers: object) -> dict[str, str]:
    """Normalize aiokafka header tuples (list[tuple[str, bytes]]) into a str map."""
    if not raw_headers:
        return {}
    decoded: dict[str, str] = {}
    for key, value in raw_headers:  # type: ignore[attr-defined]
        decoded[key] = value.decode() if isinstance(value, bytes) else str(value)
    return decoded


def _single_record(msg: KafkaMessage) -> ConsumerRecord:
    """Return the single ConsumerRecord (raw_message is a 1-tuple when batched)."""
    raw = msg.raw_message
    return raw[0] if isinstance(raw, tuple) else raw


async def _ack(msg: KafkaMessage, source: str, outcome: str) -> None:
    """Count the outcome and commit the offset."""
    MESSAGES_HANDLED.labels(broker_type=_BROKER_TYPE, source=source, outcome=outcome).inc()
    await msg.ack()


def _update_partition_gauge(msg: KafkaMessage) -> None:
    """Publish the assigned-partition count from the live consumer."""
    consumer = getattr(msg, "consumer", None)
    if consumer is None:
        return
    ASSIGNED_PARTITIONS.labels(broker_type=_BROKER_TYPE, group_id=GROUP_ID).set(len(consumer.assignment()))


def _start_metrics_server() -> None:
    """Expose Prometheus metrics on the shared worker port (bind failure is ignored)."""
    import prometheus_client  # noqa: PLC0415 — imported lazily, mirrors the worker lifecycle

    port = get_settings().metrics_worker_port
    try:
        prometheus_client.start_http_server(port)
        logger.info("Consumer metrics server started", port=port)
    except OSError as exc:
        logger.warning("Consumer metrics server could not bind — skipping", port=port, error=str(exc))
