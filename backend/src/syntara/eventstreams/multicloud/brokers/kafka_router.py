"""Kafka transport — real, first-party FastStream ``KafkaBroker`` + ``KafkaRouter``.

This is the reference implementation. Compare it side by side with ``aws_router.py``
and ``azure_router.py``: the ``# DUPLICACY RISK [BROKER-SPECIFIC]`` blocks below are
almost identical in all three files, yet none of them can be shared because the
router, decorator, connection, raw-body access and ack are typed to the transport.

Note what the handler does NOT do: there is no ``event: SomeModel`` argument. The
schema is unknown, so we take the raw bytes and run them through the shared
``pipeline`` (decode -> filter -> hand off). FastStream's parse-into-a-Pydantic-model
step is bypassed entirely — it has nothing to parse into.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from faststream import AckPolicy, Context, Depends
from faststream.kafka import KafkaBroker, KafkaRouter
from faststream.security import SASLPlaintext

from syntara.eventstreams.multicloud.dependencies import get_db_session, get_request_logger
from syntara.eventstreams.multicloud.pipeline import (
    DecodeError,
    decode_message,
    hand_off_to_workflow,
    passes_filter,
)

if TYPE_CHECKING:
    from typing import Any

    from faststream.kafka import KafkaMessage

logger = structlog.stdlib.get_logger(__name__)

# DUPLICACY RISK [BROKER-SPECIFIC]: connection + security block. Kafka speaks SASL/SSL
# via faststream.security classes. AWS uses IAM/SigV4, Azure uses SAS/connection
# strings — none of this maps across, so each broker file re-implements "how do I
# authenticate", with a different type, a different set of env, and a different
# failure mode. (Verified: faststream.security has no cloud-IAM/SAS equivalents.)
_BOOTSTRAP = "CHANGE_ME:9092"
_TOPIC = "syntara-events"
_GROUP_ID = "syntara-eventstream-kafka"
_USERNAME = "CHANGE_ME"
_TOKEN = "CHANGE_ME"  # noqa: S105 — placeholder, real secret never committed (see static_broker.py stance)


def build_kafka_broker() -> KafkaBroker:
    """Construct the Kafka broker (first-party FastStream)."""
    return KafkaBroker(_BOOTSTRAP, security=SASLPlaintext(username=_USERNAME, password=_TOKEN, use_ssl=True))


def build_kafka_router() -> KafkaRouter:
    """Build the Kafka router with the schema-agnostic subscriber attached."""
    router = KafkaRouter()

    # DUPLICACY RISK [BROKER-SPECIFIC]: the decorator. @router.subscriber for Kafka
    # takes topics + group_id + auto_offset_reset + ack_policy. The AWS equivalent
    # would take a queue URL + visibility timeout; the Azure one a subscription +
    # session id. Same intent, three incompatible signatures — this decorator cannot
    # be factored out because it is a method on the Kafka-typed router.
    @router.subscriber(
        _TOPIC,
        group_id=_GROUP_ID,
        auto_offset_reset="earliest",
        max_records=1,
        ack_policy=AckPolicy.MANUAL,
    )
    async def on_event(
        # No schema, so no `event: SomeModel` body argument: declaring one would make
        # FastStream run its Pydantic decoder (its main consume-side value-add), which
        # has nothing to parse into. We take the whole message and read the raw bytes
        # ourselves — the honest shape when the payload is unknown.
        # HOLDS (logic) / DUPLICACY (wiring): the Depends provider is shared, but this
        # `= Depends(...)` wiring line must be repeated in each broker's handler.
        db: Any = Depends(get_db_session),
        log: Any = Depends(get_request_logger),
        # DUPLICACY RISK [BROKER-SPECIFIC]: the raw message type is Kafka-only, used to
        # read the raw bytes, derive the dedup key, and ack/nack.
        msg: KafkaMessage = Context("message"),
    ) -> None:
        record = _single_record(msg)
        # DUPLICACY RISK [BROKER-SPECIFIC]: id derivation. topic-partition-offset is a
        # Kafka-only dedup key; SQS/Service Bus expose entirely different identifiers.
        message_id = f"{record.topic}-{record.partition}-{record.offset}"

        try:
            decoded = decode_message(msg.body)  # HOLDS: transport-neutral decode.
        except DecodeError:
            # Content error — can never succeed on retry. Ack-and-drop, never block
            # the partition. DUPLICACY RISK [BROKER-SPECIFIC]: ack = offset commit.
            logger.warning("kafka_message_undecodable_dropped", message_id=message_id)
            await msg.ack()
            return

        if not passes_filter(decoded):  # HOLDS: transport-neutral filter.
            # Filtered out in the listener node — no work to do, just ack.
            await msg.ack()
            return

        try:
            # HOLDS: the whole decoded message is handed off, identically on every
            # transport. This is the shared core an EDA actually cares about.
            await hand_off_to_workflow(decoded, db=db, log=log, transport="kafka", message_id=message_id)
        except Exception:
            # DUPLICACY RISK [BROKER-SPECIFIC]: transient failure -> redelivery. Kafka
            # withholds the commit via nack(); SQS changes visibility; Service Bus
            # abandons the lock. Three APIs, one intent — cannot be shared.
            logger.exception("kafka_handoff_failed", message_id=message_id)
            await msg.nack()
            raise
        # DUPLICACY RISK [BROKER-SPECIFIC]: ack on Kafka = offset commit.
        await msg.ack()

    return router


def _single_record(msg: KafkaMessage) -> Any:
    """Kafka-only: unwrap the single ConsumerRecord from raw_message."""
    raw = msg.raw_message
    return raw[0] if isinstance(raw, tuple) else raw
