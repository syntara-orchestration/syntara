"""Kafka record size validation using the pinned client's conservative estimator."""

from aiokafka.record.default_records import DefaultRecordBatchBuilder

from syntara.workflows.workflow_engine.activities.kafka_publish_errors import fail_publish
from syntara.workflows.workflow_engine.models.kafka_publish import (
    KAFKA_PUBLISH_MAX_HEADERS,
    KAFKA_PUBLISH_MAX_RECORD_BYTES,
    KafkaPublishParameters,
    encode_publish_message,
)


def compile_publish_message(
    parameters: KafkaPublishParameters,
) -> tuple[bytes, bytes | None, list[tuple[str, bytes | None]], int]:
    """Validate resolved types and independent value/key/header/batch overhead."""
    if isinstance(parameters.headers, list) and len(parameters.headers) > KAFKA_PUBLISH_MAX_HEADERS:
        fail_publish("kafka_message_too_large")
    try:
        value, key, headers = encode_publish_message(parameters)
    except (ValueError, TypeError, RecursionError):
        fail_publish("kafka_invalid_message")
    size = int(DefaultRecordBatchBuilder.estimate_size_in_bytes(key, value, headers))
    if size > KAFKA_PUBLISH_MAX_RECORD_BYTES:
        fail_publish("kafka_message_too_large")
    return value, key, headers, size
