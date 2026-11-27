"""Provide real broker operations for the opt-in Kafka Playwright tests.

The frontend E2E test invokes this helper to create and delete its disposable
Kafka test topic, inspect consumer assignments, and send or read a record.
"""

import asyncio
import base64
import json
import os
import ssl
import sys
from pathlib import Path

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.protocol.group import MemberAssignment


async def main() -> None:
    action, topic = sys.argv[1:]
    root = Path(__file__).resolve().parents[5]
    options = {
        "bootstrap_servers": os.getenv(
            "SYNTARA_E2E_KAFKA_CLIENT_BOOTSTRAP",
            os.getenv("SYNTARA_E2E_KAFKA_BOOTSTRAP", "localhost:9093"),
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
    if action == "send":
        producer = AIOKafkaProducer(**options)
        await producer.start()
        try:
            record = await producer.send_and_wait(topic, b'{"source":"subscribe-ui"}')
            print(json.dumps({"partition": record.partition, "offset": record.offset}))
        finally:
            await producer.stop()
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
        elif action == "has-consumer":
            groups = [
                group_id
                for group_id, protocol in await admin.list_consumer_groups()
                if protocol == "consumer"
            ]
            described = await admin.describe_consumer_groups(groups) if groups else []
            has_consumer = any(
                assigned_topic == topic and partitions
                for response in described
                for group in response.groups
                for member in group[5]
                if member[-1]
                for assigned_topic, partitions in MemberAssignment.decode(
                    member[-1]
                ).assignment
            )
            print(json.dumps(has_consumer))
        else:
            raise ValueError(f"Unknown fixture action: {action}")
    finally:
        await admin.close()


asyncio.run(main())
