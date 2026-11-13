"""Publish contracts, bounded late deliveries, and credential payload sizing."""

import asyncio
from typing import TYPE_CHECKING, Any, cast

import pytest
from aiokafka import TopicPartition, errors
from aiokafka.structs import RecordMetadata
from pydantic import ValidationError
from temporalio.api.common.v1 import Payloads
from temporalio.converter import DataConverter
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.kafka_publish_errors import classify_publish_error
from syntara.workflows.workflow_engine.codecs.credential_codec import CredentialPayloadCodec
from syntara.workflows.workflow_engine.models.kafka_publish import KafkaPublishParameters, encode_publish_message
from syntara.workflows.workflow_engine.services.kafka_publish_message import compile_publish_message
from syntara.workflows.workflow_engine.services.kafka_publish_pool import (
    KafkaPublishPool,
    initialize_kafka_publish_pool,
    set_kafka_publish_pool,
)
from syntara.workflows.workflow_engine.utils.temporal_argument_size import temporal_argument_size

if TYPE_CHECKING:
    from aiokafka import AIOKafkaProducer

PARAMETERS: dict[str, Any] = {
    "integration_id": "11111111-1111-4111-8111-111111111111",
    "credential_id": "22222222-2222-4222-8222-222222222222",
    "topic": "automation.outcomes",
    "payload": {"ok": True},
}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (None, b"null"),
        (False, b"false"),
        (42, b"42"),
        ([1, 2], b"[1,2]"),
        ("hello", b'"hello"'),
        ({"z": 2, "a": 1}, b'{"a":1,"z":2}'),
    ],
)
def test_json_native_value_encoding(payload: object, expected: bytes) -> None:
    parameters = KafkaPublishParameters.model_validate({**PARAMETERS, "payload": payload})
    assert encode_publish_message(parameters)[0] == expected


def test_ordered_binary_headers_and_null_empty_distinction() -> None:
    parameters = KafkaPublishParameters.model_validate(
        {
            **PARAMETERS,
            "key": {"encoding": "base64", "value": "AAEC"},
            "headers": [
                {"name": "same", "value": None},
                {"name": "same", "value": {"encoding": "utf-8", "value": ""}},
                {"name": "same", "value": {"encoding": "base64", "value": "AAEC"}},
            ],
        }
    )
    _value, key, headers = encode_publish_message(parameters)
    assert key == b"\x00\x01\x02"
    assert headers == [("same", None), ("same", b""), ("same", b"\x00\x01\x02")]


@pytest.mark.parametrize(
    "patch",
    [
        {"topic": "${trigger.topic}"},
        {"integration_id": "${trigger.integration_id}"},
        {"credential_id": "${trigger.credential_id}"},
        {"credential_id": None},
        {"topic": ".."},
        {"key": {"encoding": "utf-8", "value": 42}},
        {"headers": [{"name": "x"}]},
        {"acks": 1},
        {"partition": 0},
    ],
)
def test_invalid_parameters_rejected(patch: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        KafkaPublishParameters.model_validate({**PARAMETERS, **patch})


def test_payload_required_even_though_explicit_null_allowed() -> None:
    with pytest.raises(ValidationError):
        KafkaPublishParameters.model_validate({key: value for key, value in PARAMETERS.items() if key != "payload"})


@pytest.mark.parametrize("payload", [float("nan"), float("inf"), {1: "key"}, b"bytes", {"bad": {1, 2}}])
def test_non_json_values_fail_before_sending(payload: object) -> None:
    with pytest.raises(ApplicationError) as result:
        compile_publish_message(KafkaPublishParameters.model_validate({**PARAMETERS, "payload": payload}))
    assert result.value.type == "kafka_invalid_message"
    assert result.value.non_retryable


@pytest.mark.parametrize("value", ["not base64!", "AA EC", "AAEC\n"])
def test_binary_values_are_not_repaired(value: str) -> None:
    with pytest.raises(ApplicationError) as result:
        compile_publish_message(
            KafkaPublishParameters.model_validate({**PARAMETERS, "key": {"encoding": "base64", "value": value}})
        )
    assert result.value.type == "kafka_invalid_message"


def test_kafka_size_boundary_and_header_limit() -> None:
    # The pinned client's estimator includes variable-width record lengths.
    parameters = KafkaPublishParameters.model_validate({**PARAMETERS, "payload": "x" * 1_048_487})
    assert compile_publish_message(parameters)[3] == 1_048_576
    parameters.payload += "x"
    with pytest.raises(ApplicationError) as result:
        compile_publish_message(parameters)
    assert result.value.type == "kafka_message_too_large"
    parameters = KafkaPublishParameters.model_validate({**PARAMETERS, "headers": [{"name": "x", "value": None}] * 129})
    with pytest.raises(ApplicationError) as result:
        compile_publish_message(parameters)
    assert result.value.type == "kafka_message_too_large"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        [PARAMETERS, None, "project"],
        [
            {"_resolved_credentials": {"extra_vars": {"kafka_password": "synthetic"}}, "payload": "é" * 300_000},
            {},
            "project",
        ],
    ],
)
async def test_argument_size_matches_actual_worker_converter_and_codec(arguments: list[Any]) -> None:
    converter = DataConverter(payload_codec=CredentialPayloadCodec(b"x" * 32))
    actual = Payloads(payloads=await converter.encode(arguments)).ByteSize()
    assert temporal_argument_size(arguments) == actual


class FakeProducer:
    """A broker-acknowledged record can remain pending through caller timeouts."""

    def __init__(self) -> None:
        """Create one broker-controlled delivery future."""
        self.future: asyncio.Future[RecordMetadata] = asyncio.get_running_loop().create_future()
        self.started = 0
        self.stopped = False

    async def start(self) -> None:
        self.started += 1

    async def send(self, *args: object, **kwargs: object) -> asyncio.Future[RecordMetadata]:
        return self.future

    async def stop(self) -> None:
        await asyncio.shield(self.future)
        self.stopped = True

    def ack(self) -> None:
        self.future.set_result(RecordMetadata("outcomes", 0, TopicPartition("outcomes", 0), 9, 123, 0, 0))


@pytest.mark.asyncio
async def test_timeout_keeps_pending_capacity_until_late_acknowledgment() -> None:
    producer = FakeProducer()
    pool = KafkaPublishPool(1)
    try:
        async with pool.acquire("revision", "identity", lambda: cast("AIOKafkaProducer", producer)) as entry:
            send = await pool.submit(entry, "outcomes", b"null", None, [], 100)
            assert send.task is not None
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(send.task), timeout=0.02)
            assert send.may_have_delivered
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(pool.submit(entry, "outcomes", b"null", None, [], 100), timeout=0.02)
            producer.ack()
            assert (await send.task).offset == 9
            another = await pool.submit(entry, "outcomes", b"null", None, [], 100)
            assert another.task is not None
            await another.task
        assert producer.started == 1
    finally:
        if not producer.future.done():
            producer.ack()
        await pool.close()
    assert producer.stopped


@pytest.mark.asyncio
async def test_shutdown_wait_does_not_cancel_pending_delivery_or_cleanup() -> None:
    producer = FakeProducer()
    pool = KafkaPublishPool(1)
    async with pool.acquire("revision", "identity", lambda: cast("AIOKafkaProducer", producer)) as entry:
        send = await pool.submit(entry, "outcomes", b"null", None, [], 100)
    await pool.close(wait_seconds=0.02)
    assert not producer.future.cancelled()
    assert not producer.stopped
    assert send.task is not None
    producer.ack()
    await send.task
    await pool.close()
    assert producer.stopped


def test_unknown_errors_do_not_start_automatic_action_retry() -> None:
    assert classify_publish_error(RuntimeError("sensitive broker text")) == ("kafka_unexpected_error", False, False)


@pytest.mark.parametrize("error", [errors.NotEnoughReplicasError, errors.NotEnoughReplicasAfterAppendError])
def test_insufficient_replicas_allow_action_recovery(error: type[Exception]) -> None:
    assert classify_publish_error(error()) == ("kafka_metadata_unavailable", True, False)


@pytest.mark.asyncio
async def test_cancellation_before_delivery_task_starts_releases_reserved_capacity() -> None:
    producer = FakeProducer()
    pool = KafkaPublishPool(1)
    try:
        async with pool.acquire("revision", "identity", lambda: cast("AIOKafkaProducer", producer)) as entry:
            send = await pool.submit(entry, "outcomes", b"null", None, [], 100)
            send.cancel_before_enqueue()
            assert send.task is not None
            with pytest.raises(asyncio.CancelledError):
                await send.task
            producer.ack()
            # A second send proves both the permit and byte accounting were released.
            next_send = await asyncio.wait_for(pool.submit(entry, "outcomes", b"null", None, [], 100), timeout=1)
            assert next_send.task is not None
            await next_send.task
    finally:
        if not producer.future.done():
            producer.ack()
        await pool.close()


@pytest.mark.asyncio
async def test_worker_restart_keeps_retiring_producers_counted() -> None:
    producer = FakeProducer()
    other = FakeProducer()
    pool = KafkaPublishPool(1)
    set_kafka_publish_pool(pool)
    try:
        async with pool.acquire("first", "first", lambda: cast("AIOKafkaProducer", producer)) as entry:
            send = await pool.submit(entry, "outcomes", b"null", None, [], 100)
        await pool.close(wait_seconds=0.02)
        resumed = initialize_kafka_publish_pool(1)
        assert resumed is pool

        async def another() -> None:
            async with resumed.acquire("second", "second", lambda: cast("AIOKafkaProducer", other)):
                pass

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(another(), timeout=0.02)
        assert other.started == 0
        producer.ack()
        assert send.task is not None
        await send.task
        await another()
        assert other.started == 1
    finally:
        if not producer.future.done():
            producer.ack()
        if not other.future.done():
            other.ack()
        await pool.close()
        set_kafka_publish_pool(None)


def test_runtime_credential_is_required() -> None:
    with pytest.raises(ValidationError, match="credential_id"):
        KafkaPublishParameters.model_validate(
            {key: value for key, value in PARAMETERS.items() if key != "credential_id"}
        )
