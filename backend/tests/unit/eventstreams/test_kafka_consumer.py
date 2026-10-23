"""Kafka partition consumer: client config, epoch tracking, typed positions, lifecycle."""

from __future__ import annotations

import asyncio
import ssl
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from aiokafka import TopicPartition
from aiokafka.coordinator.assignors.roundrobin import RoundRobinPartitionAssignor
from aiokafka.errors import (
    KafkaConnectionError,
    KafkaError,
    KafkaTimeoutError,
    UnknownTopicOrPartitionError,
    UnsupportedVersionError,
)
from aiokafka.structs import OffsetAndMetadata
from pydantic import ValidationError

from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer, _RebalanceListener, _sanitize
from syntara.eventstreams.adapters.kafka_identity import MetadataResponseV10, SourceMetadataRequest
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.connection import ResolvedKafkaConnection
from syntara.eventstreams.core.consumer import MAX_POSITION_OFFSET, IdentityStatus, PositionStatus, RebalanceCallback
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
    return consumer


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
    assert kwargs["sasl_plain_username"] == conn.sasl_plain_username
    assert kwargs["sasl_plain_password"] == conn.sasl_plain_password
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
    assert adapter._consumer is None


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


def test_connection_repr_redacts_secrets() -> None:
    conn = ResolvedKafkaConnection(
        bootstrap_servers=["broker:9092"],
        security_protocol="SASL_SSL",
        sasl_mechanism="SCRAM-SHA-256",
        sasl_plain_username="user",
        sasl_plain_password="supersecret",  # noqa: S106
        ssl_context=None,
    )
    r = repr(conn)
    assert "supersecret" not in r
    assert "***" in r


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
    assert "s3cret" not in result.model_dump_json()
    assert "broker:9092" not in result.model_dump_json()
    consumer._client.get_random_node.return_value = None
    consumer._client.send.reset_mock()
    result = await adapter.observe_source_identity(expected_epoch=adapter.epoch)
    assert result.topic_id.status == IdentityStatus.UNAVAILABLE
    consumer._client.send.assert_not_awaited()
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
