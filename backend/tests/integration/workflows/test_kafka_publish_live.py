"""Opt-in activity transport check against the owned root-Compose Kafka fixture.

Start only the kafka service in project syntara-kafka-publish-implementation,
then set SYNTARA_KAFKA_PUBLISH_LIVE=1. No application database is used: resource
availability is isolated here and separately tested against database fixtures.
"""

import asyncio
import json
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from aiokafka import AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from temporalio.testing import ActivityEnvironment

from syntara.core.config.base import get_settings
from syntara.integrations.adapters.kafka import KafkaAdapter
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.workflow_engine.activities import kafka_publish_activity as module
from syntara.workflows.workflow_engine.activities.kafka_publish_connection import check_publish_topic
from syntara.workflows.workflow_engine.constants import ENGINE_TIMEOUT_SECONDS_KEY
from syntara.workflows.workflow_engine.services.kafka_publish_pool import KafkaPublishPool, set_kafka_publish_pool


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("SYNTARA_KAFKA_PUBLISH_LIVE") != "1", reason="Requires the explicitly owned Compose Kafka fixture"
)
async def test_publish_activity_round_trip_over_fixture_sasl_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify acknowledgment and actual message bytes through the real activity."""
    project = "syntara-kafka-publish-implementation"
    container = f"{project}_kafka_1"
    executable = shutil.which("podman")
    assert executable is not None
    process = await asyncio.create_subprocess_exec(executable, "inspect", container, stdout=asyncio.subprocess.PIPE)
    stdout, _stderr = await process.communicate()
    assert process.returncode == 0
    inspection = json.loads(stdout)[0]
    assert inspection["Config"]["Labels"].get("io.podman.compose.project") == project
    monkeypatch.setattr(get_settings(), "integration_url_allowed_hosts", ["localhost"])
    root = Path(__file__).resolve().parents[4]
    config = KafkaConfiguration(
        bootstrap_servers=["localhost:9093"],
        sasl_mechanism="PLAIN",
        ca_certificate=(root / "backend/.secrets/certs/ca.pem").read_text(),
    )
    credentials = {"kafka_username": "fixture", "kafka_password": "disposable-local-only"}
    options = KafkaAdapter(config).connection_options(credentials, timeout_seconds=10)
    admin = AIOKafkaAdminClient(bootstrap_servers=config.bootstrap_servers, **options)
    topic = f"syntara-publish-implementation-{uuid4().hex}"
    pool = KafkaPublishPool(2)
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=config.bootstrap_servers,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        **options,
    )
    set_kafka_publish_pool(pool)
    context = MagicMock()
    context.return_value.__aenter__ = AsyncMock()
    context.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(module, "_session_factory", context)
    monkeypatch.setattr(module, "current_publish_resources", AsyncMock(return_value=(config, "revision")))
    await admin.start()
    try:
        await admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])
        await check_publish_topic(config, credentials, topic)
        parameters = {
            "integration_id": str(uuid4()),
            "credential_id": str(uuid4()),
            "topic": topic,
            "payload": {"outcome": "completed", "items": [True, None, 42]},
            "key": {"encoding": "base64", "value": "AAEC"},
            "headers": [{"name": "x", "value": None}, {"name": "x", "value": {"encoding": "utf-8", "value": ""}}],
            "_resolved_credentials": {"extra_vars": credentials},
            "_resolved_integration": config.model_dump(mode="json"),
            "_kafka_revision": "revision",
            "_kafka_publish_deadline": (datetime.now(UTC) + timedelta(seconds=180)).isoformat(),
            ENGINE_TIMEOUT_SECONDS_KEY: 30,
        }
        result = await ActivityEnvironment().run(module.execute_kafka_publish_activity, parameters, None, str(uuid4()))
        assert result["output"]["topic"] == topic
        assert result["output"]["offset"] == "0"
        await consumer.start()
        record = await asyncio.wait_for(consumer.getone(), timeout=10)
        assert record.value == b'{"items":[true,null,42],"outcome":"completed"}'
        assert record.key == b"\x00\x01\x02"
        assert list(record.headers) == [("x", None), ("x", b"")]
    finally:
        await consumer.stop()
        await pool.close()
        set_kafka_publish_pool(None)
        await admin.delete_topics([topic])
        await admin.close()
