"""Azure transport (Service Bus) — NO first-party FastStream broker exists.

VERIFIED against FastStream 0.7.7: there is no ``faststream.azure`` /
``faststream.servicebus`` module. Same situation as AWS. This module mirrors
``kafka_router.py`` / ``aws_router.py`` to make the triplicated boilerplate obvious,
with the broker import guarded so it fails honestly rather than silently.
"""

from __future__ import annotations

from typing import Any

import structlog
from faststream import Depends

from syntara.eventstreams.multicloud.brokers.aws_router import BrokerNotAvailableError
from syntara.eventstreams.multicloud.dependencies import get_db_session, get_request_logger
from syntara.eventstreams.multicloud.pipeline import (
    DecodeError,
    decode_message,
    hand_off_to_workflow,
    passes_filter,
)

logger = structlog.stdlib.get_logger(__name__)

# DUPLICACY RISK [BROKER-SPECIFIC]: connection + security block, Azure flavour. Not
# SASL (Kafka), not IAM (AWS) — a SAS connection string / Azure AD credential plus a
# topic + subscription. A third distinct auth model in a third file.
_NAMESPACE_CONN_STR = (
    "Endpoint=sb://CHANGE_ME.servicebus.windows.net/;SharedAccessKeyName=CHANGE_ME;SharedAccessKey=CHANGE_ME"
)
_TOPIC = "syntara-events"
_SUBSCRIPTION = "syntara-eventstream-azure"
_MAX_LOCK_RENEWAL_S = 300  # Service Bus analogue of visibility timeout / offset hold


def _import_servicebus() -> tuple[Any, Any]:
    """Import a Service Bus broker/router or fail loudly (no first-party one)."""
    try:
        from faststream.azure_servicebus import (  # type: ignore[import-not-found]
            ServiceBusBroker,
            ServiceBusRouter,
        )
    except ImportError as exc:
        msg = (
            "FastStream has no first-party Azure Service Bus broker (verified: "
            "faststream.azure_servicebus does not exist). Supply a community package "
            "or author a BrokerUsecase subclass. See module docstring."
        )
        raise BrokerNotAvailableError(msg) from exc
    return ServiceBusBroker, ServiceBusRouter


def build_azure_broker() -> Any:
    """Construct the Service Bus broker (raises: no first-party broker exists)."""
    servicebus_broker, _ = _import_servicebus()
    # DUPLICACY RISK [BROKER-SPECIFIC]: construction via connection string, unlike
    # Kafka bootstrap servers or AWS region/credentials.
    return servicebus_broker(_NAMESPACE_CONN_STR)


def build_azure_router() -> Any:
    """Build the Service Bus router with the schema-agnostic subscriber attached."""
    _, servicebus_router = _import_servicebus()
    router = servicebus_router()

    # DUPLICACY RISK [BROKER-SPECIFIC]: the decorator. Service Bus needs topic +
    # subscription (+ optional session) — a third incompatible @subscriber signature.
    @router.subscriber(topic=_TOPIC, subscription=_SUBSCRIPTION)  # type: ignore[misc]
    async def on_event(
        # No schema: no body argument (see kafka_router). We read raw bytes off msg.
        db: Any = Depends(get_db_session),  # HOLDS logic / DUPLICATE wiring.
        log: Any = Depends(get_request_logger),
        msg: Any = None,  # DUPLICACY RISK [BROKER-SPECIFIC]: ServiceBusReceivedMessage type.
    ) -> None:
        # DUPLICACY RISK [BROKER-SPECIFIC]: id derivation. Service Bus has a
        # sequence_number + message_id + lock_token — yet another dedup key scheme.
        message_id = getattr(msg, "message_id", "unknown")

        try:
            decoded = decode_message(msg.body)  # HOLDS.
        except DecodeError:
            # DUPLICACY RISK [BROKER-SPECIFIC]: content error -> ack = complete().
            logger.warning("azure_message_undecodable_dropped", message_id=message_id)
            await msg.ack()
            return

        if not passes_filter(decoded):  # HOLDS.
            await msg.ack()
            return

        try:
            await hand_off_to_workflow(decoded, db=db, log=log, transport="azure", message_id=message_id)  # HOLDS.
        except Exception:
            # DUPLICACY RISK [BROKER-SPECIFIC]: redelivery = abandon() (release the
            # lock), NOT Kafka nack() nor SQS visibility change. Third distinct API.
            logger.exception("azure_handoff_failed", message_id=message_id)
            raise
        # DUPLICACY RISK [BROKER-SPECIFIC]: ack on Service Bus = complete(), not commit/delete.
        await msg.ack()

    return router
