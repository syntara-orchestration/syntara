"""Native FastStream ``TestBroker`` demonstration for the multi-cloud extension.

Schema is unknown: the handler takes raw bytes, decodes them, filters in the listener
node, and hands the WHOLE decoded message off to Temporal. These tests exercise that
pipeline in-memory (no real Kafka) and show the matching limitation: ``TestBroker`` is
per-family (``TestKafkaBroker``), and AWS/Azure cannot be tested this way because they
have no broker to test against.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from faststream.kafka import TestKafkaBroker

from syntara.eventstreams.multicloud.brokers import kafka_router
from syntara.eventstreams.multicloud.brokers.aws_router import BrokerNotAvailableError, build_aws_router
from syntara.eventstreams.multicloud.brokers.azure_router import build_azure_router


async def test_message_passing_filter_is_handed_off_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    """A decodable message that passes the filter is handed off verbatim to the workflow."""
    spy = AsyncMock()
    # Patch the reference the subscriber closes over (imported into the router module).
    monkeypatch.setattr(kafka_router, "hand_off_to_workflow", spy)

    broker = kafka_router.build_kafka_broker()
    broker.include_router(kafka_router.build_kafka_router())

    payload = b'{"event_type": "anything.at.all", "customer": "acme", "nested": {"k": 1}}'

    # TestKafkaBroker: in-memory, no real Kafka. This is a genuine FastStream win.
    async with TestKafkaBroker(broker) as test_broker:
        await test_broker.publish(payload, topic="syntara-events")

    spy.assert_awaited_once()
    # The WHOLE decoded message is forwarded — no schema, no field dropping.
    passed = spy.await_args.args[0]
    assert passed == {"event_type": "anything.at.all", "customer": "acme", "nested": {"k": 1}}
    assert spy.await_args.kwargs["transport"] == "kafka"


async def test_message_failing_filter_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A decodable message that fails the filter is acked and never handed off."""
    spy = AsyncMock()
    monkeypatch.setattr(kafka_router, "hand_off_to_workflow", spy)

    broker = kafka_router.build_kafka_broker()
    broker.include_router(kafka_router.build_kafka_router())

    # No `event_type` key -> filtered out in the listener node.
    async with TestKafkaBroker(broker) as test_broker:
        await test_broker.publish(b'{"customer": "acme"}', topic="syntara-events")

    spy.assert_not_awaited()


async def test_undecodable_message_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-JSON body is a content error: dropped (acked), never handed off, never retried."""
    spy = AsyncMock()
    monkeypatch.setattr(kafka_router, "hand_off_to_workflow", spy)

    broker = kafka_router.build_kafka_broker()
    broker.include_router(kafka_router.build_kafka_router())

    async with TestKafkaBroker(broker) as test_broker:
        await test_broker.publish(b"this is not json", topic="syntara-events")

    spy.assert_not_awaited()


def test_aws_and_azure_have_no_first_party_broker() -> None:
    """The headline finding, as a test: AWS/Azure routers cannot even be built.

    # DUPLICACY RISK [BROKER-SPECIFIC]: there is no TestSqsBroker / TestServiceBusBroker
    # to exercise these paths, so the multi-cloud consumer is untestable beyond Kafka.
    """
    with pytest.raises(BrokerNotAvailableError):
        build_aws_router()
    with pytest.raises(BrokerNotAvailableError):
        build_azure_router()
