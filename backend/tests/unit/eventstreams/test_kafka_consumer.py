"""Kafka partition consumer: client config, epoch tracking, typed positions, lifecycle."""

from __future__ import annotations

import asyncio
import ssl
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.client import AIOKafkaClient
from aiokafka.coordinator.assignors.roundrobin import RoundRobinPartitionAssignor
from aiokafka.errors import (
    KafkaConnectionError,
    KafkaError,
    KafkaTimeoutError,
    UnknownTopicOrPartitionError,
    UnsupportedVersionError,
)
from aiokafka.protocol.metadata import MetadataResponse_v0
from aiokafka.structs import OffsetAndMetadata
from pydantic import SecretStr, ValidationError

from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer, _RebalanceListener, _sanitize
from syntara.eventstreams.adapters.kafka_identity import MetadataResponseV10, SourceMetadataRequest
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.connection import ResolvedKafkaConnection
from syntara.eventstreams.core.consumer import (
    MAX_POSITION_OFFSET,
    IdentityStatus,
    PartitionSetStatus,
    PositionStatus,
    RebalanceCallback,
)
from syntara.eventstreams.core.source_metadata import EventSourceMetadata
from syntara.eventstreams.exceptions import (
    ConsumerNotRunningError,
    KafkaTransportError,
    OwnershipRevokedError,
    StaleEpochError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


def _connection() -> ResolvedKafkaConnection:
    return ResolvedKafkaConnection(
        bootstrap_servers=["broker:9092"],
        security_protocol="SASL_SSL",
        sasl_mechanism="SCRAM-SHA-256",
        sasl_plain_username="user",
        sasl_plain_password="s3cret",  # noqa: S106
        ssl_context=None,
    )


def _source_config(
    topic: str = "events.test",
    group_id: str = "syntara.deploy.sub.1",
) -> KafkaSourceConfiguration:
    return KafkaSourceConfiguration(topic=topic, group_id=group_id)


def _mock_consumer() -> AsyncMock:
    consumer = AsyncMock()
    consumer.start = AsyncMock()
    consumer.stop = AsyncMock()
    consumer.subscribe = MagicMock()
    consumer.seek = MagicMock()
    consumer.commit = AsyncMock()
    consumer.committed = AsyncMock(return_value=None)
    consumer.end_offsets = AsyncMock(return_value={})
    consumer.beginning_offsets = AsyncMock(return_value={})
    consumer._client = MagicMock()
    consumer._client.get_random_node.return_value = 1
    consumer._client.send = AsyncMock()
    consumer.pause = MagicMock()
    consumer.resume = MagicMock()
    consumer.getmany = AsyncMock(return_value={})
    return consumer


def _fetch_context() -> EventSourceMetadata:
    return EventSourceMetadata(
        integration_id=UUID(int=1),
        subscription_id=UUID(int=2),
        source_generation=1,
        received_at=datetime.now(UTC),
    )


async def test_fetch_preserves_bytes_headers_and_trusted_coordinates(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await _start_with_partitions(adapter, mock_aiokafka, {0})
    record = SimpleNamespace(
        value=b'{"count":2}',
        key=b"\xff",
        offset=44,
        timestamp=1234,
        timestamp_type=1,
        headers=[("repeat", b"\xff"), ("repeat", None), ("repeat", b"")],
    )
    mock_aiokafka.return_value.getmany.return_value = {TopicPartition(adapter.topic, 0): [record]}
    result = await adapter.fetch([0], _fetch_context(), expected_epoch=adapter.epoch, max_records=3, timeout_ms=100)
    event = result[0][0]
    assert event.value == record.value
    assert event.key == record.key
    assert [(header.name, header.value) for header in event.headers] == record.headers
    assert event.source_metadata.offset == "44"
    assert event.source_metadata.timestamp_type == "log_append_time"
    mock_aiokafka.return_value.getmany.assert_awaited_once_with(
        TopicPartition(adapter.topic, 0), timeout_ms=100, max_records=3
    )
    mock_aiokafka.return_value.commit.assert_not_awaited()
    await adapter.stop()


async def test_fetch_checks_epoch_before_and_after_broker_wait(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    listener = await _start_with_partitions(adapter, mock_aiokafka, {0})
    epoch = adapter.epoch
    with pytest.raises(StaleEpochError):
        await adapter.fetch([0], _fetch_context(), expected_epoch=epoch - 1, max_records=1, timeout_ms=1)
    mock_aiokafka.return_value.getmany.assert_not_awaited()

    async def revoke(*_args: object, **_kwargs: object) -> dict[TopicPartition, list[object]]:
        await listener.on_partitions_revoked({TopicPartition(adapter.topic, 0)})
        return {}

    mock_aiokafka.return_value.getmany.side_effect = revoke
    with pytest.raises(StaleEpochError):
        await adapter.fetch([0], _fetch_context(), expected_epoch=epoch, max_records=1, timeout_ms=1)
    await adapter.stop()


async def test_empty_paused_fetch_still_polls(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await _start_with_partitions(adapter, mock_aiokafka, {0})
    await adapter.pause([0], expected_epoch=adapter.epoch)
    assert await adapter.fetch([], _fetch_context(), expected_epoch=adapter.epoch, max_records=1, timeout_ms=1) == {}
    mock_aiokafka.return_value.getmany.assert_awaited_once_with(timeout_ms=1, max_records=1)
    await adapter.stop()


async def test_fetch_failure_is_not_a_content_result(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await _start_with_partitions(adapter, mock_aiokafka, {0})
    mock_aiokafka.return_value.getmany.side_effect = KafkaConnectionError("password=PRIVATE")
    with pytest.raises(KafkaTransportError) as failure:
        await adapter.fetch([0], _fetch_context(), expected_epoch=adapter.epoch, max_records=1, timeout_ms=1)
    assert "PRIVATE" not in str(failure.value)
    await adapter.stop()


async def test_fetch_client_options_use_deployment_overrides(mock_aiokafka, override_settings) -> None:
    with override_settings(event_fetch_max_records=3, event_queue_max_bytes=4096):
        adapter = KafkaPartitionConsumer(_connection(), _source_config())
        await adapter.start()
        options = mock_aiokafka.call_args.kwargs
        assert options["max_poll_records"] == 3
        assert options["fetch_max_bytes"] == 4096
        assert options["max_partition_fetch_bytes"] == 4096
        await adapter.stop()


@pytest.fixture
def mock_aiokafka() -> Iterator[MagicMock]:
    """Patch AIOKafkaConsumer constructor to return a mock."""
    with patch(
        "syntara.eventstreams.adapters.kafka_consumer.AIOKafkaConsumer",
        return_value=_mock_consumer(),
    ) as mock_cls:
        yield mock_cls


async def _start_with_partitions(
    adapter: KafkaPartitionConsumer,
    mock_cls: MagicMock,
    partitions: set[int],
) -> _RebalanceListener:
    """Start adapter and simulate partition assignment; return listener."""
    await adapter.start()
    listener = mock_cls.return_value.subscribe.call_args.kwargs["listener"]
    topic = adapter.topic
    await listener.on_partitions_assigned({TopicPartition(topic, p) for p in partitions})
    return cast("_RebalanceListener", listener)


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_client_constructed_with_mandated_config(mock_aiokafka: MagicMock) -> None:
    conn = _connection().model_copy(update={"ssl_context": ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)})
    cfg = _source_config()
    adapter = KafkaPartitionConsumer(conn, cfg)

    await adapter.start()

    mock_aiokafka.assert_called_once()
    kwargs = mock_aiokafka.call_args.kwargs
    assert kwargs["group_id"] == cfg.group_id
    assert kwargs["enable_auto_commit"] is False
    assert kwargs["auto_offset_reset"] == "none"
    assert kwargs["isolation_level"] == "read_committed"
    assert kwargs["security_protocol"] == "SASL_SSL"
    assert kwargs["sasl_mechanism"] == "SCRAM-SHA-256"
    assert kwargs["bootstrap_servers"] == conn.bootstrap_servers
    assert conn.sasl_plain_username is not None
    assert conn.sasl_plain_password is not None
    assert kwargs["sasl_plain_username"] == conn.sasl_plain_username.get_secret_value()
    assert kwargs["sasl_plain_password"] == conn.sasl_plain_password.get_secret_value()
    assert kwargs["ssl_context"] is conn.ssl_context
    assert kwargs["partition_assignment_strategy"] == (RoundRobinPartitionAssignor,)
    args, subscribe_kwargs = mock_aiokafka.return_value.subscribe.call_args
    assert args == ([cfg.topic],)
    assert "listener" in subscribe_kwargs

    await adapter.stop()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_start_stop_are_idempotent_and_clear_assignment(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    assert not bool(adapter.is_running)
    await _start_with_partitions(adapter, mock_aiokafka, {0, 1})
    await adapter.start()
    assert bool(adapter.is_running)
    mock_aiokafka.assert_called_once()

    await adapter.stop()
    await adapter.stop()
    assert not bool(adapter.is_running)
    assert adapter.assignment == frozenset()
    mock_aiokafka.return_value.stop.assert_awaited_once()


@pytest.mark.anyio
async def test_restart_invalidates_epoch_and_clears_assignment(mock_aiokafka: MagicMock) -> None:
    adapter, _ = await _reassigned_adapter(mock_aiokafka)
    await adapter.stop()
    mock_aiokafka.return_value = _mock_consumer()
    await adapter.start()
    assert bool(adapter.is_running)
    assert adapter.assignment == frozenset()
    assert adapter.epoch == 4
    await adapter.stop()


@pytest.mark.anyio
async def test_stop_raises_on_shutdown_error(mock_aiokafka: MagicMock) -> None:
    mock_aiokafka.return_value.stop.side_effect = KafkaError("shutdown error")
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()

    with pytest.raises(KafkaTransportError):
        await adapter.stop()

    assert not bool(adapter.is_running)
    assert adapter._consumer is mock_aiokafka.return_value
    with pytest.raises(KafkaTransportError, match="shutdown is incomplete"):
        await adapter.start()
    with pytest.raises(KafkaTransportError):
        await adapter.stop()
    assert adapter._consumer is mock_aiokafka.return_value
    assert mock_aiokafka.return_value.stop.await_count == 1


@pytest.mark.anyio
async def test_cancelled_stop_retains_consumer_for_retry(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()
    await adapter._handle_partitions_assigned({TopicPartition(adapter.topic, 0)})
    epoch = adapter.epoch
    consumer = mock_aiokafka.return_value
    entered, release = asyncio.Event(), asyncio.Event()

    async def close() -> None:
        entered.set()
        await release.wait()

    consumer.stop.side_effect = close
    async with asyncio.timeout(1):
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.01):
                await adapter.stop()
    assert entered.is_set()
    assert adapter.epoch == epoch + 1
    assert not adapter.assignment
    assert adapter._consumer is consumer
    assert adapter._stop_task is not None
    assert not adapter._stop_task.done()
    release.set()
    await adapter.stop()
    assert adapter.epoch == epoch + 1
    assert vars(adapter)["_consumer"] is None
    assert consumer.stop.await_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize("commit_fails", [False, True], ids=["drained", "drain-failed"])
async def test_stop_allows_revoke_drain_before_final_cleanup(mock_aiokafka: MagicMock, *, commit_fails: bool) -> None:
    """Shutdown keeps the assigned epoch valid while a revoke callback drains."""
    callback_epoch: int | None = None

    class _DrainCallback:
        async def on_partitions_assigned(self, partitions: frozenset[int], epoch: int) -> None:
            pass

        async def on_partitions_revoked(self, partitions: frozenset[int], epoch: int) -> None:
            nonlocal callback_epoch
            callback_epoch = epoch
            assert adapter.is_running
            await adapter.seek(0, 100, expected_epoch=epoch)
            await adapter.commit(dict.fromkeys(partitions, 100), expected_epoch=epoch)

    adapter = KafkaPartitionConsumer(_connection(), _source_config(), rebalance_callback=_DrainCallback())
    listener = await _start_with_partitions(adapter, mock_aiokafka, {0})
    assigned_epoch = adapter.epoch
    consumer = mock_aiokafka.return_value

    async def revoke_during_stop() -> None:
        await listener.on_partitions_revoked({TopicPartition(adapter.topic, 0)})

    consumer.stop.side_effect = revoke_during_stop
    if commit_fails:
        consumer.commit.side_effect = KafkaError("drain commit failed")
        with pytest.raises(KafkaTransportError):
            await adapter.stop()
    else:
        await adapter.stop()

    assert callback_epoch == assigned_epoch
    consumer.seek.assert_called_once_with(TopicPartition(adapter.topic, 0), 100)
    consumer.commit.assert_awaited_once_with({TopicPartition(adapter.topic, 0): OffsetAndMetadata(100, "")})
    assert not adapter.is_running
    assert adapter._consumer is (consumer if commit_fails else None)
    assert adapter.assignment == frozenset()
    assert adapter.epoch > assigned_epoch
    with pytest.raises(ConsumerNotRunningError):
        await adapter.commit({0: 101}, expected_epoch=assigned_epoch)
    with pytest.raises(StaleEpochError):
        await adapter.observe_source_identity(expected_epoch=assigned_epoch)
    if commit_fails:
        with pytest.raises(KafkaTransportError):
            await adapter.stop()
    else:
        await adapter.stop()
    consumer.stop.assert_awaited_once()


@pytest.mark.anyio
async def test_cancelled_stop_still_invalidates_assignment(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await _start_with_partitions(adapter, mock_aiokafka, {0})
    epoch = adapter.epoch
    mock_aiokafka.return_value.stop.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await adapter.stop()
    assert not adapter.is_running
    assert adapter._consumer is mock_aiokafka.return_value
    assert adapter.assignment == frozenset()
    assert adapter.epoch > epoch


@pytest.mark.anyio
async def test_operations_rejected_when_stopped() -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    with pytest.raises(ConsumerNotRunningError), adapter.position_operation(0, expected_epoch=0):
        pytest.fail("Stopped consumer granted a position operation")
    with pytest.raises(ConsumerNotRunningError):
        await adapter.seek(0, 100, expected_epoch=adapter.epoch)
    with pytest.raises(ConsumerNotRunningError):
        await adapter.commit({0: 100}, expected_epoch=adapter.epoch)
    with pytest.raises(ConsumerNotRunningError):
        await adapter.committed([0])
    with pytest.raises(ConsumerNotRunningError):
        await adapter.end_offsets([0])
    with pytest.raises(ConsumerNotRunningError):
        await adapter.pause([0], expected_epoch=0)
    with pytest.raises(ConsumerNotRunningError):
        await adapter.resume([0], expected_epoch=0)


async def test_position_operations_exclude_competing_calls_but_not_other_partitions(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await _start_with_partitions(adapter, mock_aiokafka, {0, 1})
    with adapter.position_operation(0, expected_epoch=adapter.epoch) as first:
        assert first
        with adapter.position_operation(0, expected_epoch=adapter.epoch) as competing:
            assert not competing
        with adapter.position_operation(1, expected_epoch=adapter.epoch) as independent:
            assert independent
    with adapter.position_operation(0, expected_epoch=adapter.epoch) as retried:
        assert retried
    await adapter.stop()


async def test_position_operation_releases_after_failure(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await _start_with_partitions(adapter, mock_aiokafka, {0})
    with pytest.raises(RuntimeError, match="failed"), adapter.position_operation(0, expected_epoch=adapter.epoch):
        msg = "failed"
        raise RuntimeError(msg)
    with adapter.position_operation(0, expected_epoch=adapter.epoch) as retried:
        assert retried
    await adapter.stop()


async def test_reassignment_does_not_release_an_outstanding_position_operation(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    listener = await _start_with_partitions(adapter, mock_aiokafka, {0})
    epoch = adapter.epoch
    with adapter.position_operation(0, expected_epoch=epoch) as first:
        assert first
        await listener.on_partitions_revoked({TopicPartition(adapter.topic, 0)})
        await listener.on_partitions_assigned({TopicPartition(adapter.topic, 0)})
        with pytest.raises(StaleEpochError), adapter.position_operation(0, expected_epoch=epoch):
            pytest.fail("Stale epoch granted a position operation")
        with adapter.position_operation(0, expected_epoch=adapter.epoch) as competing:
            assert not competing
    with adapter.position_operation(0, expected_epoch=adapter.epoch) as retried:
        assert retried
    with pytest.raises(OwnershipRevokedError), adapter.position_operation(1, expected_epoch=adapter.epoch):
        pytest.fail("Unassigned partition granted a position operation")
    await adapter.stop()


# ---------------------------------------------------------------------------
# Rebalance and epoch tracking
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_rebalance_updates_assignment_and_epoch(mock_aiokafka: MagicMock) -> None:
    callback = AsyncMock(spec=RebalanceCallback)
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"), rebalance_callback=callback)
    await adapter.start()

    listener = mock_aiokafka.return_value.subscribe.call_args.kwargs["listener"]

    assert adapter.epoch == 0
    assert adapter.assignment == frozenset()

    await listener.on_partitions_assigned({TopicPartition("t", 0), TopicPartition("t", 1)})
    assert adapter.assignment == frozenset({0, 1})
    assert adapter.epoch == 1
    callback.on_partitions_assigned.assert_awaited_once_with(frozenset({0, 1}), 1)

    await listener.on_partitions_revoked({TopicPartition("t", 1)})
    assert adapter.assignment == frozenset({0})
    assert adapter.epoch == 2
    callback.on_partitions_revoked.assert_awaited_once_with(frozenset({1}), 1)

    await listener.on_partitions_assigned({TopicPartition("t", 0), TopicPartition("t", 2)})
    assert adapter.assignment == frozenset({0, 2})
    assert adapter.epoch == 3

    await adapter.stop()


@pytest.mark.anyio
@pytest.mark.parametrize("commit_fails", [False, True], ids=["drained", "drain-failed"])
async def test_revoke_allows_drain_then_invalidates_ownership(mock_aiokafka: MagicMock, *, commit_fails: bool) -> None:
    committed_epoch: int | None = None

    class _DrainCallback:
        async def on_partitions_assigned(self, partitions: frozenset[int], epoch: int) -> None:
            pass

        async def on_partitions_revoked(self, partitions: frozenset[int], epoch: int) -> None:
            nonlocal committed_epoch
            committed_epoch = epoch
            await adapter.commit(dict.fromkeys(partitions, 100), expected_epoch=epoch)

    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"), rebalance_callback=_DrainCallback())
    listener = await _start_with_partitions(adapter, mock_aiokafka, {0, 1})

    revoked = {TopicPartition("t", 0), TopicPartition("t", 1)}
    if commit_fails:
        mock_aiokafka.return_value.commit.side_effect = KafkaError("commit failed")
        with pytest.raises(KafkaTransportError):
            await listener.on_partitions_revoked(revoked)
    else:
        await listener.on_partitions_revoked(revoked)

    assert committed_epoch == 1
    mock_aiokafka.return_value.commit.assert_awaited_once()
    assert adapter.epoch == 2
    assert adapter.assignment == frozenset()

    with pytest.raises(StaleEpochError):
        await adapter.commit({0: 101}, expected_epoch=1)

    await adapter.stop()


@pytest.mark.anyio
async def test_empty_revocation_is_noop(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await adapter.start()
    listener = mock_aiokafka.return_value.subscribe.call_args.kwargs["listener"]

    await listener.on_partitions_revoked(set())
    assert adapter.epoch == 0

    await adapter.stop()


# ---------------------------------------------------------------------------
# Stale epoch rejection
# ---------------------------------------------------------------------------


async def _reassigned_adapter(mock_cls: MagicMock) -> tuple[KafkaPartitionConsumer, _RebalanceListener]:
    """Return an adapter after an assignment, revocation, and reassignment."""
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    listener = await _start_with_partitions(adapter, mock_cls, {0})
    await listener.on_partitions_revoked({TopicPartition("t", 0)})
    await listener.on_partitions_assigned({TopicPartition("t", 0)})
    return adapter, listener


@pytest.mark.anyio
async def test_seek_rejects_stale_epoch(mock_aiokafka: MagicMock) -> None:
    adapter, _ = await _reassigned_adapter(mock_aiokafka)

    with pytest.raises(StaleEpochError, match="expected 0") as exc_info:
        await adapter.seek(0, 100, expected_epoch=0)

    assert exc_info.value.expected_epoch == 0
    assert exc_info.value.current_epoch == 3
    mock_aiokafka.return_value.seek.assert_not_called()
    await adapter.seek(0, 100, expected_epoch=adapter.epoch)
    await adapter.stop()


@pytest.mark.anyio
async def test_commit_rejects_stale_epoch(mock_aiokafka: MagicMock) -> None:
    adapter, _ = await _reassigned_adapter(mock_aiokafka)

    with pytest.raises(StaleEpochError):
        await adapter.commit({0: 42}, expected_epoch=0)

    await adapter.stop()


@pytest.mark.anyio
async def test_pause_rejects_stale_epoch(mock_aiokafka: MagicMock) -> None:
    adapter, _ = await _reassigned_adapter(mock_aiokafka)

    with pytest.raises(StaleEpochError):
        await adapter.pause([0], expected_epoch=0)

    await adapter.stop()


@pytest.mark.anyio
async def test_resume_rejects_stale_epoch(mock_aiokafka: MagicMock) -> None:
    adapter, _ = await _reassigned_adapter(mock_aiokafka)

    with pytest.raises(StaleEpochError):
        await adapter.resume([0], expected_epoch=0)

    await adapter.stop()


# ---------------------------------------------------------------------------
# Ownership checks
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_seek_rejects_unassigned_partition(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0})

    with pytest.raises(OwnershipRevokedError, match="Partition 5") as exc_info:
        await adapter.seek(5, 100, expected_epoch=adapter.epoch)

    assert exc_info.value.partition == 5
    mock_aiokafka.return_value.seek.assert_not_called()

    await adapter.stop()


@pytest.mark.anyio
async def test_commit_rejects_unassigned_partition(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0})

    with pytest.raises(OwnershipRevokedError):
        await adapter.commit({0: 10, 3: 20}, expected_epoch=adapter.epoch)

    await adapter.stop()


@pytest.mark.anyio
async def test_resume_rejects_unassigned_partition(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0})

    with pytest.raises(OwnershipRevokedError):
        await adapter.resume([0, 5], expected_epoch=adapter.epoch)

    await adapter.stop()


# ---------------------------------------------------------------------------
# Explicit commit maps
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_commit_passes_explicit_offset_map(mock_aiokafka: MagicMock) -> None:
    consumer_instance = mock_aiokafka.return_value
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0, 1})

    await adapter.commit({0: 42, 1: 99}, expected_epoch=adapter.epoch)

    consumer_instance.commit.assert_awaited_once()
    offset_map = consumer_instance.commit.call_args.args[0]
    assert offset_map[TopicPartition("t", 0)] == OffsetAndMetadata(42, "")
    assert offset_map[TopicPartition("t", 1)] == OffsetAndMetadata(99, "")

    await adapter.stop()


@pytest.mark.anyio
async def test_commit_wraps_kafka_error(mock_aiokafka: MagicMock) -> None:
    mock_aiokafka.return_value.commit.side_effect = KafkaError("commit failed password=x")
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0})

    with pytest.raises(KafkaTransportError, match="password=\\*\\*\\*"):
        await adapter.commit({0: 10}, expected_epoch=adapter.epoch)

    await adapter.stop()


# ---------------------------------------------------------------------------
# Seek error wrapping
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_seek_wraps_kafka_error(mock_aiokafka: MagicMock) -> None:
    mock_aiokafka.return_value.seek.side_effect = KafkaError("seek failed secret=abc")
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0})

    with pytest.raises(KafkaTransportError, match="secret=\\*\\*\\*"):
        await adapter.seek(0, 100, expected_epoch=adapter.epoch)

    await adapter.stop()


# ---------------------------------------------------------------------------
# Committed position reads
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_committed_unavailable_on_timeout(mock_aiokafka: MagicMock) -> None:
    consumer_instance = mock_aiokafka.return_value
    consumer_instance.committed = AsyncMock(side_effect=KafkaTimeoutError())
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()

    results = await adapter.committed([0], timeout_ms=100)
    assert results[0].status == PositionStatus.UNAVAILABLE
    assert results[0].error is not None

    await adapter.stop()


@pytest.mark.anyio
async def test_committed_unavailable_on_kafka_error(mock_aiokafka: MagicMock) -> None:
    consumer_instance = mock_aiokafka.return_value
    consumer_instance.committed = AsyncMock(side_effect=KafkaError("broker gone"))
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()

    results = await adapter.committed([0])
    assert results[0].status == PositionStatus.UNAVAILABLE
    assert results[0].error == "committed position lookup failed"

    await adapter.stop()


@pytest.mark.anyio
async def test_committed_multiple_partitions_mixed(mock_aiokafka: MagicMock) -> None:
    async def _side_effect(tp: TopicPartition) -> int | None:
        if tp.partition == 0:
            return 100
        return None

    consumer_instance = mock_aiokafka.return_value
    consumer_instance.committed = AsyncMock(side_effect=_side_effect)
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0, 1})

    results = await adapter.committed([0, 1, 5])
    assert results[0].status == PositionStatus.VERIFIED
    assert results[0].offset == 100
    assert results[1].status == PositionStatus.ABSENT
    assert results[1].offset is None
    assert results[5].status == PositionStatus.UNCERTAIN
    assert results[5].offset is None
    assert results[5].error is not None

    await adapter.stop()


# ---------------------------------------------------------------------------
# End offsets (visible-end boundary)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_end_offsets_unavailable_on_timeout(mock_aiokafka: MagicMock) -> None:
    consumer_instance = mock_aiokafka.return_value
    consumer_instance.end_offsets = AsyncMock(side_effect=KafkaTimeoutError())
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()

    results = await adapter.end_offsets([0], timeout_ms=100)
    assert results[0].status == PositionStatus.UNAVAILABLE

    await adapter.stop()


@pytest.mark.anyio
async def test_end_offsets_distinguishes_verified_missing_and_unknown_partitions(mock_aiokafka: MagicMock) -> None:
    tp0 = TopicPartition("events.test", 0)
    consumer_instance = mock_aiokafka.return_value
    consumer_instance.end_offsets = AsyncMock(return_value={tp0: 100, TopicPartition("events.test", 2): -1})
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()

    results = await adapter.end_offsets([0, 1, 2])
    assert results[0].status == PositionStatus.VERIFIED
    assert results[0].offset == 100
    assert results[1].status == PositionStatus.UNCERTAIN
    assert results[1].offset is None
    assert results[2].status == PositionStatus.UNCERTAIN
    assert results[2].offset is None

    await adapter.stop()


@pytest.mark.anyio
async def test_end_offsets_unavailable_on_kafka_error(mock_aiokafka: MagicMock) -> None:
    consumer_instance = mock_aiokafka.return_value
    consumer_instance.end_offsets = AsyncMock(side_effect=KafkaError("not available"))
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()

    results = await adapter.end_offsets([0, 1])
    assert results[0].status == PositionStatus.UNAVAILABLE
    assert results[1].status == PositionStatus.UNAVAILABLE

    await adapter.stop()


# ---------------------------------------------------------------------------
# Pause / resume
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pause_and_resume(mock_aiokafka: MagicMock) -> None:
    consumer_instance = mock_aiokafka.return_value
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0, 1})

    await adapter.pause([0, 1], expected_epoch=adapter.epoch)
    consumer_instance.pause.assert_called_once()
    paused_tps = set(consumer_instance.pause.call_args.args)
    assert TopicPartition("t", 0) in paused_tps
    assert TopicPartition("t", 1) in paused_tps

    await adapter.resume([0], expected_epoch=adapter.epoch)
    consumer_instance.resume.assert_called_once()
    resumed_tps = set(consumer_instance.resume.call_args.args)
    assert TopicPartition("t", 0) in resumed_tps

    await adapter.stop()


@pytest.mark.anyio
async def test_pause_rejects_unassigned_partition(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0})

    with pytest.raises(OwnershipRevokedError):
        await adapter.pause([0, 5], expected_epoch=adapter.epoch)

    await adapter.stop()


# ---------------------------------------------------------------------------
# Error sanitization
# ---------------------------------------------------------------------------


def test_sanitize_scrubs_credentials() -> None:
    raw = "KafkaConnectionError: password=s3cret username=admin sasl_plain_password=abc"
    cleaned = _sanitize(raw)
    assert "s3cret" not in cleaned
    assert "admin" not in cleaned
    assert "abc" not in cleaned
    assert "password=***" in cleaned


@pytest.mark.anyio
async def test_start_wraps_kafka_error(mock_aiokafka: MagicMock) -> None:
    mock_aiokafka.return_value.start.side_effect = KafkaConnectionError("Cannot connect password=secret")
    adapter = KafkaPartitionConsumer(_connection(), _source_config())

    with pytest.raises(KafkaTransportError, match="password=\\*\\*\\*"):
        await adapter.start()

    mock_aiokafka.return_value.stop.assert_awaited_once()
    assert not bool(adapter.is_running)
    await adapter.stop()
    mock_aiokafka.return_value.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# ResolvedKafkaConnection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("representation", ["repr", "str", "dict", "model_dump", "json_dump", "model_dump_json"])
def test_connection_outputs_redact_secrets(representation: str) -> None:
    conn = ResolvedKafkaConnection(
        bootstrap_servers=["broker:9092"],
        security_protocol="SASL_SSL",
        sasl_mechanism="SCRAM-SHA-256",
        sasl_plain_username="private-runtime-principal",
        sasl_plain_password="supersecret",  # noqa: S106
        ssl_context=None,
    )
    output = {
        "repr": repr(conn),
        "str": str(conn),
        "dict": str(dict(conn)),
        "model_dump": str(conn.model_dump()),
        "json_dump": str(conn.model_dump(mode="json")),
        "model_dump_json": conn.model_dump_json(),
    }[representation]
    assert "supersecret" not in output
    assert "private-runtime-principal" not in output
    assert isinstance(conn.sasl_plain_username, SecretStr)
    assert isinstance(conn.sasl_plain_password, SecretStr)
    assert str(conn) == repr(conn)
    # Explicit include requests must not override the credential exclusion.
    assert conn.model_dump(include={"sasl_plain_username", "sasl_plain_password"}) == {}


@pytest.mark.anyio
@pytest.mark.parametrize("authenticated", [False, True])
async def test_credentials_are_unwrapped_only_for_consumer_construction(
    mock_aiokafka: MagicMock, *, authenticated: bool
) -> None:
    username = "private-runtime-principal" if authenticated else None
    password = "  secret with spaces  " if authenticated else None
    connection = ResolvedKafkaConnection(
        bootstrap_servers=["broker:9092"],
        security_protocol="SASL_SSL" if authenticated else "SSL",
        sasl_plain_username=username,
        sasl_plain_password=password,
    )
    adapter = KafkaPartitionConsumer(connection, _source_config())
    await adapter.start()
    kwargs = mock_aiokafka.call_args.kwargs
    assert kwargs["sasl_plain_username"] == username
    assert kwargs["sasl_plain_password"] == password
    await adapter.stop()


def test_connection_frozen() -> None:
    conn = _connection()
    with pytest.raises(ValidationError):
        conn.security_protocol = "PLAINTEXT"


def test_connection_has_ssl_context() -> None:
    conn_without = _connection()
    assert not conn_without.has_ssl_context()

    conn_with = ResolvedKafkaConnection(
        bootstrap_servers=["b:9092"],
        security_protocol="SSL",
        ssl_context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
    )
    assert conn_with.has_ssl_context()


@pytest.mark.anyio
async def test_beginning_offsets_validates_each_exact_partition(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await _start_with_partitions(adapter, mock_aiokafka, {0})
    consumer = mock_aiokafka.return_value
    values = [0, MAX_POSITION_OFFSET, -1, MAX_POSITION_OFFSET + 1, None, True, 1.5, "12"]
    consumer.beginning_offsets.return_value = {
        TopicPartition(adapter.topic, partition): value for partition, value in enumerate(values)
    }
    consumer.beginning_offsets.return_value[TopicPartition("other-topic", 8)] = 10
    result = await adapter.beginning_offsets(range(9), expected_epoch=adapter.epoch)
    assert [result[p].offset for p in (0, 1)] == [0, MAX_POSITION_OFFSET]
    assert all(result[p].status == PositionStatus.UNCERTAIN for p in range(2, 9))
    consumer.beginning_offsets.assert_awaited_once_with([TopicPartition(adapter.topic, p) for p in range(9)])
    consumer.seek.assert_not_called()
    consumer.commit.assert_not_awaited()
    # Observing an unassigned partition cannot authorize a subsequent write.
    with pytest.raises(OwnershipRevokedError):
        await adapter.seek(1, 0, expected_epoch=adapter.epoch)
    with pytest.raises(OwnershipRevokedError):
        await adapter.commit({1: 0}, expected_epoch=adapter.epoch)
    await adapter.stop()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (UnknownTopicOrPartitionError(), PositionStatus.UNCERTAIN),
        (KafkaError("sasl password=s3cret broker:9092"), PositionStatus.UNAVAILABLE),
        (KafkaTimeoutError(), PositionStatus.UNAVAILABLE),
    ],
)
async def test_beginning_offsets_failures_are_explicit_and_sanitized(
    mock_aiokafka: MagicMock, error: Exception, status: PositionStatus
) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await _start_with_partitions(adapter, mock_aiokafka, {0})
    mock_aiokafka.return_value.beginning_offsets.side_effect = error
    result = await adapter.beginning_offsets([0, 1], expected_epoch=adapter.epoch)
    assert all(item.status == status and item.offset is None for item in result.values())
    assert "s3cret" not in str(result)
    assert "broker:9092" not in str(result)
    await adapter.stop()


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["beginning", "identity"])
async def test_observation_timeouts_cancel_pending_io(mock_aiokafka: MagicMock, operation: str) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await _start_with_partitions(adapter, mock_aiokafka, {0})
    cancelled = asyncio.Event()

    async def pending(*args: object) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    consumer = mock_aiokafka.return_value
    if operation == "beginning":
        consumer.beginning_offsets.side_effect = pending
        positions = await adapter.beginning_offsets([0], expected_epoch=adapter.epoch, timeout_ms=1)
        assert positions[0].status == PositionStatus.UNAVAILABLE
    else:
        consumer._client.send.side_effect = pending
        identity = await adapter.observe_source_identity(expected_epoch=adapter.epoch, timeout_ms=1)
        assert identity.topic_id.status == IdentityStatus.UNAVAILABLE
        assert identity.partitions.status == PartitionSetStatus.UNAVAILABLE
        assert identity.partitions.partition_ids is None
    assert cancelled.is_set()
    await adapter.stop()


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["beginning", "end", "committed", "identity"])
@pytest.mark.parametrize("transition", ["reassign", "revoke", "restart"])
async def test_observations_reject_assignment_changes_during_io(
    mock_aiokafka: MagicMock, operation: str, transition: str
) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    listener = await _start_with_partitions(adapter, mock_aiokafka, {0})
    epoch = adapter.epoch

    async def changed(*args: object) -> object:
        if transition == "reassign":
            await listener.on_partitions_assigned({TopicPartition(adapter.topic, 0)})
        elif transition == "revoke":
            await listener.on_partitions_revoked({TopicPartition(adapter.topic, 0)})
        else:
            await adapter.stop()
            await adapter.start()
        if operation == "identity":
            return MetadataResponse_v0(brokers=[], topics=[(0, adapter.topic, [(0, 0, 1, [1], [1])])])
        return {TopicPartition(adapter.topic, 0): 10} if operation != "committed" else 10

    consumer = mock_aiokafka.return_value
    if operation == "identity":
        consumer._client.send.side_effect = changed
    else:
        getattr(
            consumer, {"beginning": "beginning_offsets", "end": "end_offsets", "committed": "committed"}[operation]
        ).side_effect = changed
    with pytest.raises(StaleEpochError):
        if operation == "identity":
            await adapter.observe_source_identity(expected_epoch=epoch)
        elif operation == "beginning":
            await adapter.beginning_offsets([0], expected_epoch=epoch)
        elif operation == "end":
            await adapter.end_offsets([0], expected_epoch=epoch)
        else:
            await adapter.committed([0], expected_epoch=epoch)
    # A stale epoch also prevents starting another broker lookup.
    consumer.beginning_offsets.reset_mock()
    consumer._client.send.reset_mock()
    with pytest.raises(StaleEpochError):
        await adapter.beginning_offsets([0], expected_epoch=epoch)
    with pytest.raises(StaleEpochError):
        await adapter.observe_source_identity(expected_epoch=epoch)
    consumer.beginning_offsets.assert_not_awaited()
    consumer._client.send.assert_not_awaited()
    await adapter.stop()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (UnsupportedVersionError(), IdentityStatus.UNSUPPORTED),
        (KafkaError("password=s3cret broker:9092"), IdentityStatus.UNAVAILABLE),
        (ValueError("password=s3cret"), IdentityStatus.UNCERTAIN),
        (UnknownTopicOrPartitionError(), IdentityStatus.UNKNOWN_TOPIC),
    ],
)
async def test_identity_failures_never_claim_verified_identifiers(
    mock_aiokafka: MagicMock, error: Exception, status: IdentityStatus
) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await _start_with_partitions(adapter, mock_aiokafka, {0})
    consumer = mock_aiokafka.return_value
    consumer._client.send.side_effect = error
    result = await adapter.observe_source_identity(expected_epoch=adapter.epoch)
    assert result.topic_id.status == status
    assert result.cluster_id.status != IdentityStatus.VERIFIED
    assert result.topic_id.value is None
    assert result.partitions.status == (
        PartitionSetStatus.UNCERTAIN if status == IdentityStatus.UNCERTAIN else PartitionSetStatus.UNAVAILABLE
    )
    assert result.partitions.partition_ids is None
    assert "s3cret" not in result.model_dump_json()
    assert "broker:9092" not in result.model_dump_json()
    consumer._client.get_random_node.return_value = None
    consumer._client.send.reset_mock()
    result = await adapter.observe_source_identity(expected_epoch=adapter.epoch)
    assert result.topic_id.status == IdentityStatus.UNAVAILABLE
    assert result.partitions.status == PartitionSetStatus.UNAVAILABLE
    assert result.partitions.partition_ids is None
    consumer._client.send.assert_not_awaited()
    await adapter.stop()


@pytest.mark.anyio
async def test_metadata_observes_full_topic_and_added_partitions(mock_aiokafka: MagicMock) -> None:
    """Membership is refreshed independently of assignment and without moving offsets."""
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await _start_with_partitions(adapter, mock_aiokafka, {1})
    consumer = mock_aiokafka.return_value
    epoch = adapter.epoch
    observations = []
    for count in (3, 4):
        consumer._client.send.return_value = MetadataResponseV10(
            throttle_time_ms=0,
            brokers=[],
            cluster_id="cluster-A",
            controller_id=1,
            topics=[
                (
                    0,
                    adapter.topic,
                    UUID(int=1),
                    False,
                    [(0, partition, 1, 7, [1], [1], [], {}) for partition in range(count)],
                    0,
                    {},
                )
            ],
            cluster_authorized_operations=0,
            tags={},
        )
        result = await adapter.observe_source_identity(expected_epoch=epoch)
        assert result.partitions.status == PartitionSetStatus.VERIFIED
        assert result.partitions.partition_ids == tuple(range(count))
        assert result.assignment_epoch == epoch
        observations.append(result)
    assert observations[0].partitions.partition_ids == (0, 1, 2)
    assert consumer._client.send.await_count == 2
    assert adapter.assignment == frozenset({1})
    for call in consumer._client.send.call_args_list:
        node, request = call.args
        assert node == 1
        assert isinstance(request, SourceMetadataRequest)
        assert request.prepare({3: (0, 10)}).to_object()["allow_auto_topic_creation"] is False
    consumer.seek.assert_not_called()
    consumer.commit.assert_not_awaited()
    consumer.getmany.assert_not_awaited()
    await adapter.stop()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error", [KafkaError("password=s3cret"), ValueError("password=s3cret"), IndexError("password=s3cret")]
)
async def test_failed_metadata_io_still_rejects_stale_epoch(mock_aiokafka: MagicMock, error: Exception) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    listener = await _start_with_partitions(adapter, mock_aiokafka, {0})
    epoch = adapter.epoch

    async def revoked(*args: object) -> None:
        await listener.on_partitions_revoked({TopicPartition(adapter.topic, 0)})
        raise error

    mock_aiokafka.return_value._client.send.side_effect = revoked
    with pytest.raises(StaleEpochError):
        await adapter.observe_source_identity(expected_epoch=epoch)
    await adapter.stop()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "topics",
    [
        [(0,)],
        [(0, "events.test", [(0, 0)])],
        [(0, "events.test", [(0, 0, 1, [1], [1]), (0,)])],
    ],
)
async def test_short_metadata_rows_return_sanitized_uncertain_evidence(
    mock_aiokafka: MagicMock, topics: list[tuple[object, ...]]
) -> None:
    """Real schema traversal can fail before membership validation runs."""
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await _start_with_partitions(adapter, mock_aiokafka, {0})
    mock_aiokafka.return_value._client.send.return_value = MetadataResponse_v0(brokers=[], topics=topics)
    result = await adapter.observe_source_identity(expected_epoch=adapter.epoch)
    assert result.partitions.status == PartitionSetStatus.UNCERTAIN
    assert result.partitions.partition_ids is None
    assert result.partitions.error == "invalid metadata response"
    await adapter.stop()


@pytest.mark.anyio
async def test_identity_observation_uses_authenticated_transport_without_granting_ownership(
    mock_aiokafka: MagicMock,
) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await _start_with_partitions(adapter, mock_aiokafka, set())
    consumer = mock_aiokafka.return_value
    consumer._client.send.return_value = MetadataResponseV10(
        throttle_time_ms=0,
        brokers=[],
        cluster_id="cluster-A",
        controller_id=1,
        topics=[(0, adapter.topic, UUID(int=1), False, [], 0, {})],
        cluster_authorized_operations=0,
        tags={},
    )
    result = await adapter.observe_source_identity(expected_epoch=adapter.epoch)
    assert result.assignment_epoch == adapter.epoch
    assert result.topic == adapter.topic
    assert result.cluster_id.value == "cluster-A"
    assert result.topic_id.status == IdentityStatus.VERIFIED
    node, request = consumer._client.send.call_args.args
    assert node == 1
    assert isinstance(request, SourceMetadataRequest)
    assert request.topic == adapter.topic
    assert adapter.assignment == frozenset()
    consumer.seek.assert_not_called()
    consumer.commit.assert_not_awaited()
    await adapter.stop()


@pytest.mark.anyio
async def test_installed_aiokafka_metadata_transport_contract() -> None:
    """Guard the private client boundary against changes in the pinned dependency."""
    connection = _connection().model_copy(update={"ssl_context": ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)})
    adapter = KafkaPartitionConsumer(connection, _source_config())
    # Keep real consumer construction/subscription/cleanup; prevent network startup.
    with patch.object(AIOKafkaConsumer, "start", new_callable=AsyncMock):
        await adapter.start()
    try:
        consumer = adapter._consumer
        assert isinstance(consumer, AIOKafkaConsumer)
        client = consumer._client
        assert isinstance(client, AIOKafkaClient)
        response = MetadataResponse_v0(brokers=[], topics=[(0, adapter.topic, [(0, 0, 1, [1], [1])])])
        with (
            patch.object(client, "get_random_node", autospec=True, return_value=1),
            patch.object(client, "send", autospec=True, return_value=response) as send,
        ):
            result = await adapter.observe_source_identity(expected_epoch=adapter.epoch)
        assert result.partitions.status == PartitionSetStatus.VERIFIED
        assert result.partitions.partition_ids == (0,)
        node, request = send.call_args.args
        assert node == 1
        assert isinstance(request, SourceMetadataRequest)
        assert request.topic == adapter.topic
    finally:
        await adapter.stop()
