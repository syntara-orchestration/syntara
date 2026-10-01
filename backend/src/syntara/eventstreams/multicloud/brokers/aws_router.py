"""AWS transport (SQS/SNS) — NO first-party FastStream broker exists.

VERIFIED against FastStream 0.7.7: there is no ``faststream.sqs`` / ``faststream.sns``
/ ``faststream.aws`` module. The only broker families FastStream ships are kafka,
confluent, rabbit, nats, redis, mqtt. So to put AWS "under FastStream" you must
either (a) depend on a community package that tracks FastStream's internals, or
(b) author a broker yourself against ``faststream.BrokerUsecase`` (parser, publisher,
subscriber, ack, AsyncAPI spec — a large surface).

This module is written as the SQS router *would* look, mirroring ``kafka_router.py``
line for line, so the duplication is visible. The broker import is guarded: calling
``build_aws_router()`` without a real SQS broker raises a clear error instead of
pretending. THIS FILE IS THE SINGLE BIGGEST FINDING: the roadmap's headline
transport is not supported by the framework at all.
"""

from __future__ import annotations

from typing import Any

import structlog
from faststream import Depends

from syntara.eventstreams.multicloud.dependencies import get_db_session, get_request_logger
from syntara.eventstreams.multicloud.pipeline import (
    DecodeError,
    decode_message,
    hand_off_to_workflow,
    passes_filter,
)

logger = structlog.stdlib.get_logger(__name__)

# DUPLICACY RISK [BROKER-SPECIFIC]: connection + security block, AWS flavour. Kafka
# used SASLPlaintext; here it would be an IAM role / SigV4 signer / boto3 session and
# a queue URL. Nothing carries over from kafka_router.py.
_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/000000000000/syntara-events"
_AWS_REGION = "us-east-1"
_VISIBILITY_TIMEOUT_S = 300  # SQS analogue of "don't redeliver while processing"


class BrokerNotAvailableError(RuntimeError):
    """Raised when a transport has no first-party FastStream broker installed."""


def _import_sqs() -> tuple[Any, Any]:
    """Import an SQS broker/router or fail loudly (there is no first-party one)."""
    try:
        # There is no such module in FastStream today; a third-party package would
        # have to provide these with the exact FastStream Router/Broker contracts.
        from faststream.sqs import SqsBroker, SqsRouter  # type: ignore[import-not-found]
    except ImportError as exc:
        msg = (
            "FastStream has no first-party AWS SQS broker (verified: faststream.sqs "
            "does not exist). Supply a community package or author a BrokerUsecase "
            "subclass. See module docstring."
        )
        raise BrokerNotAvailableError(msg) from exc
    return SqsBroker, SqsRouter


def build_aws_broker() -> Any:
    """Construct the SQS broker (raises: no first-party broker exists)."""
    sqs_broker, _ = _import_sqs()
    # DUPLICACY RISK [BROKER-SPECIFIC]: broker construction differs entirely — region,
    # credentials, queue URL vs Kafka's bootstrap servers + SASL.
    return sqs_broker(region_name=_AWS_REGION)


def build_aws_router() -> Any:
    """Build the SQS router with the schema-agnostic subscriber attached.

    The body below is intentionally a near-copy of ``kafka_router.build_kafka_router``
    — that near-identity IS the finding. Only the transport plumbing (decorator, raw
    access, id, ack) differs; the decode -> filter -> hand off core is the same shared
    ``pipeline`` used by every broker.
    """
    _, sqs_router = _import_sqs()
    router = sqs_router()

    # DUPLICACY RISK [BROKER-SPECIFIC]: the decorator. Same intent as Kafka's
    # @router.subscriber, but SQS-typed: a queue URL + visibility timeout + long-poll
    # wait instead of topic/group/offset. The whole decorator must be rewritten.
    @router.subscriber(_QUEUE_URL, visibility_timeout=_VISIBILITY_TIMEOUT_S)  # type: ignore[misc]
    async def on_event(
        # No schema: no body argument (see kafka_router). We read raw bytes off msg.
        db: Any = Depends(get_db_session),  # HOLDS logic / DUPLICATE wiring.
        log: Any = Depends(get_request_logger),
        msg: Any = None,  # DUPLICACY RISK [BROKER-SPECIFIC]: SQS message type, not KafkaMessage.
    ) -> None:
        # DUPLICACY RISK [BROKER-SPECIFIC]: id derivation. SQS has a MessageId +
        # ReceiptHandle, not topic-partition-offset — a different dedup key scheme.
        message_id = getattr(msg, "message_id", "unknown")

        try:
            decoded = decode_message(msg.body)  # HOLDS.
        except DecodeError:
            # DUPLICACY RISK [BROKER-SPECIFIC]: content error -> ack = DeleteMessage.
            logger.warning("aws_message_undecodable_dropped", message_id=message_id)
            await msg.ack()
            return

        if not passes_filter(decoded):  # HOLDS.
            await msg.ack()
            return

        try:
            await hand_off_to_workflow(decoded, db=db, log=log, transport="aws", message_id=message_id)  # HOLDS.
        except Exception:
            # DUPLICACY RISK [BROKER-SPECIFIC]: redelivery = change_message_visibility
            # / do-not-delete, NOT Kafka's nack(). Different call, same intent.
            logger.exception("aws_handoff_failed", message_id=message_id)
            raise
        # DUPLICACY RISK [BROKER-SPECIFIC]: ack on SQS = DeleteMessage, not offset commit.
        await msg.ack()

    return router
