"""Publish wire contract and broker-side limits, run in the ordinary CI suite."""

import asyncio
import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, ConsumerRecord
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import Worker
from testcontainers.community.kafka import KafkaContainer
from testcontainers.core.container import ExecConfig

from syntara.core.config.base import get_settings
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader
from syntara.eventstreams.core.filter_input import EventFilterInput
from syntara.eventstreams.core.filtering import PreparedSubscriptionFilter
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder
from syntara.eventstreams.models.filter_configuration import FilterConfiguration
from syntara.filtering.models.result import FilterOutcome
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.workflow_engine.activities import kafka_publish_activity as sender
from syntara.workflows.workflow_engine.activities import kafka_publish_connection as preparation
from syntara.workflows.workflow_engine.activities.event_subscribe_trigger import event_subscribe_trigger
from syntara.workflows.workflow_engine.activities.kafka_publish_connection import check_publish_topic
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.constants import ENGINE_TIMEOUT_SECONDS_KEY
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.services.kafka_publish_pool import KafkaPublishPool, set_kafka_publish_pool
from tests.fixtures.settings import FakeSettingsCache


class _AtomicKafkaContainer(KafkaContainer):
    """Expose the startup script only after the Docker archive upload finishes."""

    def create_file(self, content: bytes, path: str) -> None:
        # KafkaContainer waits for file existence, not upload completion. A
        # partially uploaded (even empty) script can otherwise exit successfully.
        staging_path = f"{path}.pending"
        super().create_file(content, staging_path)
        result = self.exec(ExecConfig(command=["mv", staging_path, path], user="root"))
        if result.exit_code != 0:
            msg = "Unable to publish the complete Kafka startup script"
            raise RuntimeError(msg)


@pytest.fixture(scope="module")
def kafka_broker() -> Generator[str]:
    """Use an isolated KRaft broker with implicit topic creation disabled."""
    with (
        _AtomicKafkaContainer("confluentinc/cp-kafka:7.8.0")
        .with_kraft()
        .with_env("KAFKA_AUTO_CREATE_TOPICS_ENABLE", "false") as broker
    ):
        yield broker.get_bootstrap_server()


async def test_wire_values_missing_topic_and_lower_broker_limit(
    kafka_broker: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = kafka_broker.rsplit(":", 1)[0]
    monkeypatch.setattr(get_settings(), "integration_url_allowed_hosts", [host])
    config = KafkaConfiguration(bootstrap_servers=[kafka_broker], security_protocol="PLAINTEXT", allow_plaintext=True)
    admin = AIOKafkaAdminClient(bootstrap_servers=kafka_broker)
    topic, small, missing = (f"publish-{uuid4().hex}" for _ in range(3))
    pool = KafkaPublishPool(2)
    set_kafka_publish_pool(pool)
    context = MagicMock()
    context.return_value.__aenter__ = AsyncMock()
    context.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(sender, "_session_factory", context)
    monkeypatch.setattr(sender, "current_publish_resources", AsyncMock(return_value=(config, "revision")))
    consumer = AIOKafkaConsumer(
        topic, bootstrap_servers=kafka_broker, enable_auto_commit=False, auto_offset_reset="earliest"
    )
    base: dict[str, Any] = {
        "integration_id": str(uuid4()),
        "credential_id": str(uuid4()),
        "topic": topic,
        "_resolved_credentials": {"extra_vars": {}},
        "_resolved_integration": config.model_dump(mode="json"),
        "_kafka_revision": "revision",
        "_kafka_publish_deadline": (datetime.now(UTC) + timedelta(seconds=180)).isoformat(),
        ENGINE_TIMEOUT_SECONDS_KEY: 30,
    }
    await admin.start()
    try:
        await admin.create_topics(
            [
                NewTopic(topic, num_partitions=1, replication_factor=1),
                NewTopic(small, num_partitions=1, replication_factor=1, topic_configs={"max.message.bytes": "256"}),
            ]
        )
        await check_publish_topic(config, {}, topic)
        with pytest.raises(ApplicationError) as absent:
            await check_publish_topic(config, {}, missing)
        assert absent.value.type == "kafka_topic_not_found"
        assert missing not in await admin.list_topics()
        cases: list[tuple[Any, bytes, dict[str, str] | None, bytes | None]] = [
            ({"z": 2, "a": 1}, b'{"a":1,"z":2}', {"encoding": "utf-8", "value": "café"}, "café".encode()),
            ([1, True, None], b"[1,true,null]", {"encoding": "base64", "value": "AAEC"}, b"\x00\x01\x02"),
            ("hello", b'"hello"', {"encoding": "utf-8", "value": ""}, b""),
            (42, b"42", None, None),
            (False, b"false", None, None),
            (None, b"null", None, None),
        ]
        await consumer.start()
        for payload, expected, key, expected_key in cases:
            parameters = {
                **base,
                "payload": payload,
                "key": key,
                "headers": [
                    {"name": "same", "value": None},
                    {"name": "same", "value": {"encoding": "utf-8", "value": ""}},
                    {"name": "same", "value": {"encoding": "base64", "value": "AAEC"}},
                ],
            }
            result = await ActivityEnvironment().run(sender.execute_kafka_publish_activity, parameters, None, "project")
            record = await asyncio.wait_for(consumer.getone(), timeout=10)
            assert record.value == expected
            assert record.key == expected_key
            assert list(record.headers) == [("same", None), ("same", b""), ("same", b"\x00\x01\x02")]
            assert result["output"]["offset"] == str(record.offset)
            assert result["output"]["timestamp_ms"] == record.timestamp
        with pytest.raises(ApplicationError) as oversized:
            await ActivityEnvironment().run(
                sender.execute_kafka_publish_activity, {**base, "topic": small, "payload": "x" * 1024}, None, "project"
            )
        assert oversized.value.type == "kafka_message_too_large"
        assert oversized.value.non_retryable
    finally:
        await consumer.stop()
        await pool.close()
        set_kafka_publish_pool(None)
        await admin.delete_topics([topic, small])
        await admin.close()


def _raw_record(record: ConsumerRecord[bytes, bytes], integration_id: UUID) -> RawEvent:
    return RawEvent(
        value=record.value,
        key=record.key,
        headers=tuple(RawEventHeader(name=name, value=value) for name, value in record.headers),
        source_metadata=KafkaSourceMetadata(
            integration_id=integration_id,
            subscription_id=UUID(int=2),
            source_generation=1,
            received_at=datetime.now(UTC),
            topic=record.topic,
            partition=record.partition,
            offset=str(record.offset),
        ),
    )


def _incoming_cloud_event(binding: str) -> tuple[bytes, list[tuple[str, bytes]]]:
    data = {"order_id": "order-123", "outcome": "completed"}
    attributes = {"specversion": "1.0", "id": "original-event", "type": "com.example.order", "source": "/orders"}
    if binding == "structured":
        return json.dumps({**attributes, "data": data}).encode(), [("content-type", b"application/cloudevents+json")]
    return json.dumps(data).encode(), [
        ("content-type", b"application/json"),
        *((f"ce_{name}", value.encode()) for name, value in attributes.items()),
    ]


def _round_trip_definition(parameters: dict[str, Any], incoming_topic: str) -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "CloudEvents round trip",
        "triggers": [
            {
                "id": "trigger",
                "type": "event_subscribe_trigger",
                "parameters": {
                    "integration_id": parameters["integration_id"],
                    "credential_id": parameters["credential_id"],
                    "topic": incoming_topic,
                },
            }
        ],
        "nodes": [{"id": "publish", "type": "kafka_publish", "parameters": parameters}],
        "edges": [{"from": "trigger", "to": "publish"}],
    }


def _assert_round_trip_record(record: ConsumerRecord[bytes, bytes], integration_id: UUID) -> None:
    assert record.value == b'{"order_id":"order-123","outcome":"completed"}'
    assert record.key == b"order-123"
    assert list(record.headers).count(("content-type", b"application/json")) == 1
    headers = dict(record.headers)
    event_id = headers["ce_id"]
    assert event_id is not None
    assert UUID(event_id.decode()).version == 4
    assert event_id != b"original-event"
    decoded_event = _raw_record(record, integration_id)
    decoded = JsonEventDecoder().decode(decoded_event)
    assert isinstance(decoded, EventDecodeSuccess)
    assert decoded.envelope.payload == {"order_id": "order-123", "outcome": "completed"}
    filtered = PreparedSubscriptionFilter(
        FilterConfiguration(
            expression='input.cloudevents.type == "com.example.order" && input.payload.value.outcome == "completed"'
        )
    )
    assert filtered.evaluate(EventFilterInput.from_event(decoded_event, decoded)).outcome == FilterOutcome.MATCH


async def _execute_round_trip(
    temporal_env: WorkflowEnvironment, definition: dict[str, Any], inputs: dict[str, Any], queue: str
) -> dict[str, Any]:
    handle = await temporal_env.client.start_workflow(
        OrchestratorWorkflow.run,
        args=[
            definition,
            str(uuid4()),
            "trigger",
            inputs,
            True,
            None,
            None,
            None,
            {"workflow_context": {"workflow": {"project_id": str(uuid4())}}},
        ],
        id=f"cloud-events-{uuid4()}",
        task_queue=queue,
        execution_timeout=timedelta(minutes=2),
    )
    try:
        return await asyncio.wait_for(handle.result(), timeout=45)
    except TimeoutError:
        history = await handle.fetch_history()
        failures = [
            (
                event.workflow_task_failed_event_attributes.failure.message,
                event.workflow_task_failed_event_attributes.failure.cause.message,
            )
            for event in history.events
            if event.HasField("workflow_task_failed_event_attributes")
        ]
        await handle.terminate("Round-trip test exceeded its time budget")
        pytest.fail(f"CloudEvents workflow stalled; latest workflow-task failures: {failures[-2:]}")


@pytest.mark.parametrize("binding", ["structured", "binary"])
async def test_subscribe_workflow_cloud_events_publish_round_trip(
    kafka_broker: str, temporal_env: WorkflowEnvironment, monkeypatch: pytest.MonkeyPatch, binding: str
) -> None:
    monkeypatch.setattr("syntara.settings.cache.settings_cache._runtime_settings", FakeSettingsCache())
    monkeypatch.setattr(get_settings(), "integration_url_allowed_hosts", [kafka_broker.rsplit(":", 1)[0]])
    config = KafkaConfiguration(bootstrap_servers=[kafka_broker], security_protocol="PLAINTEXT", allow_plaintext=True)
    session = MagicMock()
    session.return_value.__aenter__, session.return_value.__aexit__ = AsyncMock(), AsyncMock(return_value=False)
    for module in (sender, preparation):
        monkeypatch.setattr(module, "_session_factory", session)
        monkeypatch.setattr(module, "current_publish_resources", AsyncMock(return_value=(config, "revision")))
    incoming_topic, outgoing_topic = (f"cloud-events-{uuid4().hex}" for _ in range(2))
    integration_id = uuid4()
    parameters = {
        "integration_id": str(integration_id),
        "credential_id": str(uuid4()),
        "topic": outgoing_topic,
        "cloudevents_mode": True,
        "ce_type": "${trigger.cloudevents.type}",
        "ce_source": "/workflows/orders",
        "payload": "${trigger.payload}",
        "key": {"encoding": "utf-8", "value": "${trigger.payload.order_id}"},
    }
    admin = AIOKafkaAdminClient(bootstrap_servers=kafka_broker)
    producer = AIOKafkaProducer(bootstrap_servers=kafka_broker)
    consumer = AIOKafkaConsumer(
        incoming_topic,
        outgoing_topic,
        bootstrap_servers=kafka_broker,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    pool = KafkaPublishPool(2)
    set_kafka_publish_pool(pool)
    await admin.start()
    try:
        await admin.create_topics(
            [NewTopic(topic, num_partitions=1, replication_factor=1) for topic in (incoming_topic, outgoing_topic)]
        )
        await producer.start()
        await consumer.start()
        value, headers = _incoming_cloud_event(binding)
        await producer.send_and_wait(incoming_topic, value=value, key=b"order-123", headers=headers)
        incoming = await asyncio.wait_for(consumer.getone(), timeout=10)
        decoded = JsonEventDecoder().decode(_raw_record(incoming, integration_id))
        assert isinstance(decoded, EventDecodeSuccess)
        queue = f"cloud-events-{uuid4()}"
        async with Worker(
            temporal_env.client,
            task_queue=queue,
            workflows=[OrchestratorWorkflow],
            activities=[
                event_subscribe_trigger,
                fetch_workflow_runtime_settings,
                preparation.prepare_kafka_publish,
                sender.execute_kafka_publish_activity,
            ],
        ):
            result = await _execute_round_trip(
                temporal_env,
                _round_trip_definition(parameters, incoming_topic),
                decoded.envelope.model_dump(mode="json"),
                queue,
            )
        assert result["status"] == "completed"
        outgoing = await asyncio.wait_for(consumer.getone(), timeout=10)
        assert outgoing.topic == outgoing_topic
        _assert_round_trip_record(outgoing, integration_id)
    finally:
        await consumer.stop()
        await producer.stop()
        await pool.close()
        set_kafka_publish_pool(None)
        await admin.delete_topics([incoming_topic, outgoing_topic])
        await admin.close()
