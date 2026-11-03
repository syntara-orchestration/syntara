"""Provision and inspect records in the opt-in disposable Kafka fixture."""

import asyncio
import base64
import json
import os
import ssl
import sys
from pathlib import Path

from aiokafka import AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic


async def main() -> None:
    action, topic = sys.argv[1:]
    root = Path(__file__).resolve().parents[5]
    options = {
        "bootstrap_servers": os.getenv(
            "SYNTARA_E2E_KAFKA_BOOTSTRAP", "host.containers.internal:9093"
        ),
        "security_protocol": "SASL_SSL",
        "sasl_mechanism": "PLAIN",
        "sasl_plain_username": "fixture",
        "sasl_plain_password": "disposable-local-only",
        "ssl_context": ssl.create_default_context(
            cafile=root / "backend/.secrets/certs/ca.pem"
        ),
    }
    if action == "consume":
        consumer = AIOKafkaConsumer(
            topic, auto_offset_reset="earliest", enable_auto_commit=False, **options
        )
        await consumer.start()
        try:
            record = await asyncio.wait_for(consumer.getone(), timeout=30)
            print(
                json.dumps(
                    {
                        "value": base64.b64encode(record.value).decode(),
                        "key": base64.b64encode(record.key).decode()
                        if record.key is not None
                        else None,
                        "headers": [
                            [
                                name,
                                base64.b64encode(value).decode()
                                if value is not None
                                else None,
                            ]
                            for name, value in record.headers
                        ],
                        "topic": record.topic,
                        "partition": record.partition,
                        "offset": str(record.offset),
                    }
                )
            )
        finally:
            await consumer.stop()
        return
    admin = AIOKafkaAdminClient(**options)
    await admin.start()
    try:
        if action == "create":
            await admin.create_topics(
                [NewTopic(topic, num_partitions=1, replication_factor=1)]
            )
        elif action == "delete":
            await admin.delete_topics([topic])
        else:
            raise ValueError("Expected create, consume, or delete")
    finally:
        await admin.close()


asyncio.run(main())
