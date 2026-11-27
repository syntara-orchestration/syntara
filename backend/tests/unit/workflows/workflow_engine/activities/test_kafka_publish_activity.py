"""Kafka Publish activities preserve uncertainty, snapshots and cancellation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from aiokafka import TopicPartition
from aiokafka.structs import RecordMetadata
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.integrations.adapters.kafka_tls import KafkaMTLSContext
from syntara.integrations.models.integration_configuration import KafkaConfiguration
from syntara.workflows.workflow_engine.activities import kafka_publish_activity as module
from syntara.workflows.workflow_engine.activities.kafka_publish_errors import publish_failure
from syntara.workflows.workflow_engine.constants import ENGINE_TIMEOUT_SECONDS_KEY
from syntara.workflows.workflow_engine.services.kafka_publish_pool import KafkaPublishPool, set_kafka_publish_pool
from tests.fixtures.tls import generate_self_signed_cert

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def expire_publish_attempt(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    """Expire the real activity timeout after the intended publish phase starts."""
    deadlines: list[asyncio.Timeout] = []

    def controlled_timeout(_seconds: float | None) -> asyncio.Timeout:
        # Bound a broken setup without racing it against the behavior under test.
        deadline = asyncio.Timeout(asyncio.get_running_loop().time() + 10)
        deadlines.append(deadline)
        return deadline

    # The activity looks up asyncio.timeout on the shared asyncio module.
    monkeypatch.setattr(asyncio, "timeout", controlled_timeout)

    def expire() -> None:
        deadlines[-1].reschedule(asyncio.get_running_loop().time())

    return expire


@pytest_asyncio.fixture
async def publisher(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Provide a real bounded pool with a broker-controlled producer future."""
    future: asyncio.Future[RecordMetadata] = asyncio.get_running_loop().create_future()
    producer = MagicMock()
    producer.start = AsyncMock()
    producer.send = AsyncMock(return_value=future)
    producer.stop = AsyncMock()
    constructor = MagicMock(return_value=producer)
    monkeypatch.setattr(module, "create_kafka_publish_producer", constructor)
    monkeypatch.setattr(activity, "info", lambda: SimpleNamespace(attempt=1))
    monkeypatch.setattr(activity, "heartbeat", MagicMock())
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock()
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(module, "_session_factory", session_factory)
    config = KafkaConfiguration(bootstrap_servers=["broker.example.com:9093"])
    resources = AsyncMock(return_value=(config, "current-secret-revision", "Kafka"))
    monkeypatch.setattr(module, "current_publish_resources", resources)
    pool = KafkaPublishPool(1)
    set_kafka_publish_pool(pool)
    inputs = {
        "integration_id": "11111111-1111-4111-8111-111111111111",
        "credential_id": "22222222-2222-4222-8222-222222222222",
        "topic": "outcomes",
        "payload": None,
        "_resolved_integration": config.model_dump(mode="json"),
        "_resolved_credentials": {
            "extra_vars": {"kafka_username": "synthetic", "kafka_password": "original-synthetic"}
        },
        "_kafka_revision": "original-secret-revision",
        "_kafka_publish_deadline": (datetime.now(UTC) + timedelta(seconds=180)).isoformat(),
        ENGINE_TIMEOUT_SECONDS_KEY: 1,
    }
    return SimpleNamespace(
        future=future, producer=producer, constructor=constructor, pool=pool, inputs=inputs, resources=resources
    )


async def _cleanup(publisher: SimpleNamespace) -> None:
    if not publisher.future.done():
        publisher.future.set_result(RecordMetadata("outcomes", 0, TopicPartition("outcomes", 0), 99, 123, 0, 0))
    await publisher.pool.close()
    set_kafka_publish_pool(None)


@pytest.mark.asyncio
async def test_acknowledgment_returns_only_metadata_and_keeps_frozen_secret(publisher: SimpleNamespace) -> None:
    publisher.future.set_result(
        RecordMetadata("outcomes", 2, TopicPartition("outcomes", 2), 9_007_199_254_740_999, 123, 0, 0)
    )
    try:
        result = await module.execute_kafka_publish_activity(publisher.inputs, None, "project")
        assert result == {
            "output": {"topic": "outcomes", "partition": 2, "offset": "9007199254740999", "timestamp_ms": 123}
        }
        options = publisher.constructor.call_args.kwargs
        assert options["acks"] == "all"
        assert options["enable_idempotence"] is True
        assert (
            options["sasl_plain_password"] == publisher.inputs["_resolved_credentials"]["extra_vars"]["kafka_password"]
        )
        assert options["request_timeout_ms"] == 10_000
        publisher.producer.send.assert_awaited_once_with("outcomes", value=b"null", key=None, headers=[])
    finally:
        await _cleanup(publisher)


@pytest.mark.asyncio
async def test_acknowledged_unavailable_metadata_does_not_retry(publisher: SimpleNamespace) -> None:
    publisher.future.set_result(RecordMetadata("outcomes", 0, TopicPartition("outcomes", 0), -1, -1, 0, 0))
    try:
        result = await module.execute_kafka_publish_activity(publisher.inputs, None, "project")
        assert result["output"]["offset"] is None
        assert result["output"]["timestamp_ms"] is None
        assert publisher.producer.send.await_count == 1
    finally:
        await _cleanup(publisher)


@pytest.mark.asyncio
async def test_timeout_retains_late_delivery_and_returns_uncertainty(
    publisher: SimpleNamespace, expire_publish_attempt: Callable[[], None]
) -> None:
    def enqueue(*_args: object, **_kwargs: object) -> asyncio.Future[RecordMetadata]:
        expire_publish_attempt()
        return cast("asyncio.Future[RecordMetadata]", publisher.future)

    publisher.producer.send.side_effect = enqueue
    try:
        with pytest.raises(ApplicationError) as error:
            await module.execute_kafka_publish_activity(publisher.inputs, None, "project")
        assert error.value.type == "kafka_timeout"
        assert not error.value.non_retryable
        assert error.value.details[0]["output"]["delivery_status"] == "unconfirmed"
        publisher.producer.send.assert_awaited_once()
        assert not publisher.future.cancelled()
    finally:
        await _cleanup(publisher)


@pytest.mark.asyncio
@pytest.mark.parametrize("attempt", [1, 2])
async def test_revoked_resource_does_not_send_and_preserves_prior_uncertainty(
    publisher: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, attempt: int
) -> None:
    monkeypatch.setattr(activity, "info", lambda: SimpleNamespace(attempt=attempt))
    publisher.resources.side_effect = publish_failure("kafka_invalid_reference")
    try:
        with pytest.raises(ApplicationError) as error:
            await module.execute_kafka_publish_activity(publisher.inputs, None, "project")
        assert error.value.type == "kafka_invalid_reference"
        assert error.value.non_retryable
        assert error.value.details[0]["output"]["delivery_status"] == ("not_sent" if attempt == 1 else "unconfirmed")
        publisher.constructor.assert_not_called()
    finally:
        await _cleanup(publisher)


@pytest.mark.asyncio
async def test_connection_change_stops_retry_without_redirecting(publisher: SimpleNamespace) -> None:
    publisher.resources.return_value = (
        KafkaConfiguration(bootstrap_servers=["different.example.com:9093"]),
        "new",
        "Kafka",
    )
    try:
        with pytest.raises(ApplicationError) as error:
            await module.execute_kafka_publish_activity(publisher.inputs, None, "project")
        assert error.value.type == "kafka_connection_settings_changed"
        assert error.value.non_retryable
        publisher.constructor.assert_not_called()
    finally:
        await _cleanup(publisher)


@pytest.mark.asyncio
async def test_revocation_after_capacity_admission_prevents_the_send(publisher: SimpleNamespace) -> None:
    config = KafkaConfiguration.model_validate(publisher.inputs["_resolved_integration"])
    publisher.resources.side_effect = [(config, "revision", "Kafka"), publish_failure("kafka_invalid_reference")]
    try:
        with pytest.raises(ApplicationError) as error:
            await module.execute_kafka_publish_activity(publisher.inputs, None, "project")
        assert error.value.type == "kafka_invalid_reference"
        assert error.value.details[0]["output"]["delivery_status"] == "not_sent"
        publisher.producer.send.assert_not_awaited()
    finally:
        await _cleanup(publisher)


@pytest.mark.parametrize("rotate_before_send", [False, True])
async def test_rotating_mtls_identity_blocks_prepared_publish(
    publisher: SimpleNamespace, tmp_path: Path, *, rotate_before_send: bool
) -> None:
    config = KafkaConfiguration(bootstrap_servers=["broker.example.com:9093"], security_protocol="SSL")
    certificate, private_key = generate_self_signed_cert(tmp_path, "publish client", "client")
    publisher.inputs["_resolved_integration"] = config.model_dump(mode="json")
    publisher.inputs["_resolved_credentials"] = {
        "credential_type_name": "mTLS Client Identity",
        "extra_vars": {
            "mtls_client_certificate": certificate.read_text(),
            "mtls_client_private_key": private_key.read_text(),
        },
    }
    prepared = (config, publisher.inputs["_kafka_revision"], "mTLS Client Identity")
    rotated = (config, "rotated-identity-revision", "mTLS Client Identity")
    publisher.resources.side_effect = [prepared, rotated] if rotate_before_send else [rotated]
    try:
        with pytest.raises(ApplicationError) as error:
            await module.execute_kafka_publish_activity(publisher.inputs, None, "project")
        assert error.value.type == "kafka_connection_settings_changed"
        assert error.value.details[0]["output"]["delivery_status"] == "not_sent"
        publisher.producer.send.assert_not_awaited()
        if rotate_before_send:
            assert isinstance(publisher.constructor.call_args.kwargs["ssl_context"], KafkaMTLSContext)
        else:
            publisher.constructor.assert_not_called()
    finally:
        await _cleanup(publisher)


@pytest.mark.asyncio
async def test_cancellation_stays_cancelled_without_cancelling_delivery(publisher: SimpleNamespace) -> None:
    started = asyncio.Event()

    async def send(*args: object, **kwargs: object) -> asyncio.Future[RecordMetadata]:
        started.set()
        return cast("asyncio.Future[RecordMetadata]", publisher.future)

    publisher.producer.send.side_effect = send
    task = asyncio.create_task(module.execute_kafka_publish_activity(publisher.inputs, None, "project"))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not publisher.future.cancelled()
        heartbeat = cast("MagicMock", activity.heartbeat)
        assert heartbeat.call_args.args[0]["delivery_status"] == "unconfirmed"
    finally:
        await _cleanup(publisher)


@pytest.mark.asyncio
async def test_sensitive_unknown_error_is_terminal_and_sanitized(publisher: SimpleNamespace) -> None:
    publisher.producer.send.side_effect = RuntimeError("password=do-not-expose message=private")
    try:
        with pytest.raises(ApplicationError) as error:
            await module.execute_kafka_publish_activity(publisher.inputs, None, "project")
        assert error.value.type == "kafka_unexpected_error"
        assert error.value.non_retryable
        assert "do-not-expose" not in str(error.value.details)
        assert "private" not in str(error.value)
        assert error.value.details[0]["output"]["delivery_status"] == "not_sent"
    finally:
        await _cleanup(publisher)


@pytest.mark.asyncio
async def test_cancellation_while_waiting_to_enqueue_prevents_later_send(publisher: SimpleNamespace) -> None:
    waiting = asyncio.Event()
    available = asyncio.Event()
    enqueued = asyncio.Event()

    async def send(*args: object, **kwargs: object) -> asyncio.Future[RecordMetadata]:
        waiting.set()
        await available.wait()
        enqueued.set()
        return cast("asyncio.Future[RecordMetadata]", publisher.future)

    publisher.producer.send.side_effect = send
    task = asyncio.create_task(module.execute_kafka_publish_activity(publisher.inputs, None, "project"))
    try:
        await asyncio.wait_for(waiting.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        available.set()
        await asyncio.sleep(0)
        assert not enqueued.is_set()
        assert not publisher.future.cancelled()
    finally:
        await _cleanup(publisher)


@pytest.mark.asyncio
async def test_startup_timeout_is_distinct_from_worker_capacity(
    publisher: SimpleNamespace, expire_publish_attempt: Callable[[], None]
) -> None:
    ready = asyncio.Event()

    async def start() -> None:
        expire_publish_attempt()
        await ready.wait()

    publisher.producer.start.side_effect = start
    try:
        with pytest.raises(ApplicationError) as error:
            await module.execute_kafka_publish_activity(publisher.inputs, None, "project")
        assert error.value.type == "kafka_timeout"
        assert error.value.details[0]["output"]["delivery_status"] == "not_sent"
        publisher.producer.send.assert_not_awaited()
    finally:
        ready.set()
        await _cleanup(publisher)


@pytest.mark.asyncio
async def test_pending_delivery_holds_capacity_for_subsequent_invocation(
    publisher: SimpleNamespace, expire_publish_attempt: Callable[[], None]
) -> None:
    def enqueue(*_args: object, **_kwargs: object) -> asyncio.Future[RecordMetadata]:
        expire_publish_attempt()
        return cast("asyncio.Future[RecordMetadata]", publisher.future)

    def check_before_capacity(*_args: object) -> tuple[KafkaConfiguration, str]:
        expire_publish_attempt()
        return KafkaConfiguration.model_validate(publisher.inputs["_resolved_integration"]), "current-secret-revision"

    publisher.producer.send.side_effect = enqueue
    try:
        with pytest.raises(ApplicationError) as first:
            await module.execute_kafka_publish_activity(publisher.inputs, None, "project")
        assert first.value.details[0]["output"]["delivery_status"] == "unconfirmed"
        publisher.resources.side_effect = check_before_capacity
        with pytest.raises(ApplicationError) as second:
            await module.execute_kafka_publish_activity(publisher.inputs, None, "project")
        assert second.value.type == "kafka_capacity_unavailable"
        assert second.value.details[0]["output"]["delivery_status"] == "not_sent"
        assert publisher.producer.send.await_count == 1
    finally:
        await _cleanup(publisher)
