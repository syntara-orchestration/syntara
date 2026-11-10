"""Publish wire contract and broker-side limits, run in the ordinary CI suite."""

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from aiokafka import AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment
from testcontainers.community.kafka import KafkaContainer
from testcontainers.core.container import ExecConfig

from syntara.core.config.base import get_settings
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.workflow_engine.activities import kafka_publish_activity as sender
from syntara.workflows.workflow_engine.activities.kafka_publish_connection import check_publish_topic
from syntara.workflows.workflow_engine.constants import ENGINE_TIMEOUT_SECONDS_KEY
from syntara.workflows.workflow_engine.services.kafka_publish_pool import KafkaPublishPool, set_kafka_publish_pool


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
