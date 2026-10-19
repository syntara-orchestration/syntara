"""Kafka partition consumer: client config, epoch tracking, typed positions, lifecycle."""

from __future__ import annotations

import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokafka import TopicPartition
from aiokafka.errors import KafkaConnectionError, KafkaError, KafkaTimeoutError
from aiokafka.structs import OffsetAndMetadata
from pydantic import ValidationError

from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer, _sanitize
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.connection import ResolvedKafkaConnection
from syntara.eventstreams.core.consumer import CommittedPositionResult, PositionStatus, RebalanceCallback
from syntara.eventstreams.exceptions import (
    ConsumerNotRunningError,
    KafkaTransportError,
    OwnershipRevokedError,
    StaleEpochError,
)


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
    consumer.pause = MagicMock()
    consumer.resume = MagicMock()
    consumer.assignment = MagicMock(return_value=set())
    return consumer


@pytest.fixture
def mock_aiokafka() -> MagicMock:
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
) -> MagicMock:
    """Start adapter and simulate partition assignment; return listener."""
    await adapter.start()
    listener = mock_cls.return_value.subscribe.call_args.kwargs["listener"]
    topic = adapter.topic
    await listener.on_partitions_assigned({TopicPartition(topic, p) for p in partitions})
    return listener


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_client_constructed_with_mandated_config(mock_aiokafka: MagicMock) -> None:
    conn = _connection()
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

    await adapter.stop()


@pytest.mark.anyio
async def test_client_uses_roundrobin_assignor(mock_aiokafka: MagicMock) -> None:
    from aiokafka.coordinator.assignors.roundrobin import RoundRobinPartitionAssignor

    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()

    kwargs = mock_aiokafka.call_args.kwargs
    assert RoundRobinPartitionAssignor in kwargs["partition_assignment_strategy"]

    await adapter.stop()


@pytest.mark.anyio
async def test_subscribe_called_with_topic_and_listener(mock_aiokafka: MagicMock) -> None:
    consumer_instance = mock_aiokafka.return_value
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="my.topic"))
    await adapter.start()

    consumer_instance.subscribe.assert_called_once()
    args, kwargs = consumer_instance.subscribe.call_args
    assert args[0] == ["my.topic"]
    assert "listener" in kwargs

    await adapter.stop()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_start_sets_running(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    assert not adapter.is_running
    await adapter.start()
    assert adapter.is_running
    await adapter.stop()
    assert not adapter.is_running


@pytest.mark.anyio
async def test_start_idempotent(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()
    await adapter.start()
    mock_aiokafka.assert_called_once()
    await adapter.stop()


@pytest.mark.anyio
async def test_stop_after_partial_start(mock_aiokafka: MagicMock) -> None:
    mock_aiokafka.return_value.start.side_effect = KafkaConnectionError("fail")
    adapter = KafkaPartitionConsumer(_connection(), _source_config())

    with pytest.raises(KafkaTransportError):
        await adapter.start()

    assert not adapter.is_running
    await adapter.stop()


@pytest.mark.anyio
async def test_stop_idempotent(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()
    await adapter.stop()
    await adapter.stop()


@pytest.mark.anyio
async def test_stop_clears_assignment(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0, 1, 2})
    assert adapter.assignment == frozenset({0, 1, 2})
    await adapter.stop()
    assert adapter.assignment == frozenset()


@pytest.mark.anyio
async def test_stop_handles_consumer_stop_error(mock_aiokafka: MagicMock) -> None:
    mock_aiokafka.return_value.stop.side_effect = KafkaError("shutdown error")
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()
    await adapter.stop()
    assert not adapter.is_running


@pytest.mark.anyio
async def test_operations_rejected_when_stopped() -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    with pytest.raises(ConsumerNotRunningError):
        await adapter.seek(0, 100, expected_epoch=0)
    with pytest.raises(ConsumerNotRunningError):
        await adapter.commit({0: 100}, expected_epoch=0)
    with pytest.raises(ConsumerNotRunningError):
        await adapter.committed([0])
    with pytest.raises(ConsumerNotRunningError):
        await adapter.end_offsets([0])
    with pytest.raises(ConsumerNotRunningError):
        await adapter.pause([0], expected_epoch=0)
    with pytest.raises(ConsumerNotRunningError):
        await adapter.resume([0], expected_epoch=0)


# ---------------------------------------------------------------------------
# Rebalance and epoch tracking
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_rebalance_updates_assignment_and_epoch(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await adapter.start()

    listener = mock_aiokafka.return_value.subscribe.call_args.kwargs["listener"]

    assert adapter.epoch == 0
    assert adapter.assignment == frozenset()

    await listener.on_partitions_assigned({TopicPartition("t", 0), TopicPartition("t", 1)})
    assert adapter.assignment == frozenset({0, 1})
    assert adapter.epoch == 0

    await listener.on_partitions_revoked({TopicPartition("t", 1)})
    assert adapter.assignment == frozenset({0})
    assert adapter.epoch == 1

    await listener.on_partitions_assigned({TopicPartition("t", 0), TopicPartition("t", 2)})
    assert adapter.assignment == frozenset({0, 2})
    assert adapter.epoch == 1

    await adapter.stop()


@pytest.mark.anyio
async def test_full_revoke_then_reassign(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    listener = await _start_with_partitions(adapter, mock_aiokafka, {0, 1, 2})

    await listener.on_partitions_revoked({TopicPartition("t", p) for p in [0, 1, 2]})
    assert adapter.assignment == frozenset()
    assert adapter.epoch == 1

    await listener.on_partitions_assigned({TopicPartition("t", 3), TopicPartition("t", 4)})
    assert adapter.assignment == frozenset({3, 4})
    assert adapter.epoch == 1

    await adapter.stop()


@pytest.mark.anyio
async def test_multiple_rebalance_cycles_increment_epoch(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    listener = await _start_with_partitions(adapter, mock_aiokafka, {0})

    for _i in range(5):
        await listener.on_partitions_revoked({TopicPartition("t", 0)})
        await listener.on_partitions_assigned({TopicPartition("t", 0)})

    assert adapter.epoch == 5

    await adapter.stop()


@pytest.mark.anyio
async def test_rebalance_callback_invoked(mock_aiokafka: MagicMock) -> None:
    callback = AsyncMock(spec=RebalanceCallback)
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"), rebalance_callback=callback)
    await adapter.start()

    listener = mock_aiokafka.return_value.subscribe.call_args.kwargs["listener"]
    await listener.on_partitions_assigned({TopicPartition("t", 0)})
    callback.on_partitions_assigned.assert_awaited_once_with(frozenset({0}), 0)

    await listener.on_partitions_revoked({TopicPartition("t", 0)})
    callback.on_partitions_revoked.assert_awaited_once_with(frozenset({0}), 1)

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


async def _adapter_at_epoch_1(mock_cls: MagicMock) -> tuple[KafkaPartitionConsumer, MagicMock]:
    """Return an adapter at epoch 1 with partition 0 assigned."""
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    listener = await _start_with_partitions(adapter, mock_cls, {0})
    await listener.on_partitions_revoked({TopicPartition("t", 0)})
    await listener.on_partitions_assigned({TopicPartition("t", 0)})
    return adapter, listener


@pytest.mark.anyio
async def test_seek_rejects_stale_epoch(mock_aiokafka: MagicMock) -> None:
    adapter, _ = await _adapter_at_epoch_1(mock_aiokafka)

    with pytest.raises(StaleEpochError, match="expected 0"):
        await adapter.seek(0, 100, expected_epoch=0)

    await adapter.seek(0, 100, expected_epoch=1)
    await adapter.stop()


@pytest.mark.anyio
async def test_commit_rejects_stale_epoch(mock_aiokafka: MagicMock) -> None:
    adapter, _ = await _adapter_at_epoch_1(mock_aiokafka)

    with pytest.raises(StaleEpochError):
        await adapter.commit({0: 42}, expected_epoch=0)

    await adapter.stop()


@pytest.mark.anyio
async def test_pause_rejects_stale_epoch(mock_aiokafka: MagicMock) -> None:
    adapter, _ = await _adapter_at_epoch_1(mock_aiokafka)

    with pytest.raises(StaleEpochError):
        await adapter.pause([0], expected_epoch=0)

    await adapter.stop()


@pytest.mark.anyio
async def test_resume_rejects_stale_epoch(mock_aiokafka: MagicMock) -> None:
    adapter, _ = await _adapter_at_epoch_1(mock_aiokafka)

    with pytest.raises(StaleEpochError):
        await adapter.resume([0], expected_epoch=0)

    await adapter.stop()


@pytest.mark.anyio
async def test_stale_epoch_carries_expected_and_current(mock_aiokafka: MagicMock) -> None:
    adapter, _ = await _adapter_at_epoch_1(mock_aiokafka)

    with pytest.raises(StaleEpochError) as exc_info:
        await adapter.seek(0, 0, expected_epoch=0)

    assert exc_info.value.expected_epoch == 0
    assert exc_info.value.current_epoch == 1

    await adapter.stop()


# ---------------------------------------------------------------------------
# Ownership checks
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_seek_rejects_unassigned_partition(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0})

    with pytest.raises(OwnershipRevokedError, match="Partition 5"):
        await adapter.seek(5, 100, expected_epoch=0)

    await adapter.stop()


@pytest.mark.anyio
async def test_commit_rejects_unassigned_partition(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0})

    with pytest.raises(OwnershipRevokedError):
        await adapter.commit({0: 10, 3: 20}, expected_epoch=0)

    await adapter.stop()


@pytest.mark.anyio
async def test_resume_rejects_unassigned_partition(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0})

    with pytest.raises(OwnershipRevokedError):
        await adapter.resume([0, 5], expected_epoch=0)

    await adapter.stop()


@pytest.mark.anyio
async def test_ownership_error_carries_partition(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0})

    with pytest.raises(OwnershipRevokedError) as exc_info:
        await adapter.seek(7, 0, expected_epoch=0)

    assert exc_info.value.partition == 7

    await adapter.stop()


# ---------------------------------------------------------------------------
# Explicit commit maps
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_commit_passes_explicit_offset_map(mock_aiokafka: MagicMock) -> None:
    consumer_instance = mock_aiokafka.return_value
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0, 1})

    await adapter.commit({0: 42, 1: 99}, expected_epoch=0)

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
        await adapter.commit({0: 10}, expected_epoch=0)

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
        await adapter.seek(0, 100, expected_epoch=0)

    await adapter.stop()


# ---------------------------------------------------------------------------
# Committed position reads
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_committed_verified(mock_aiokafka: MagicMock) -> None:
    consumer_instance = mock_aiokafka.return_value
    consumer_instance.committed = AsyncMock(return_value=42)
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()

    results = await adapter.committed([0])
    assert results[0].status == PositionStatus.VERIFIED
    assert results[0].offset == 42

    await adapter.stop()


@pytest.mark.anyio
async def test_committed_absent(mock_aiokafka: MagicMock) -> None:
    consumer_instance = mock_aiokafka.return_value
    consumer_instance.committed = AsyncMock(return_value=None)
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()

    results = await adapter.committed([0])
    assert results[0].status == PositionStatus.ABSENT
    assert results[0].offset is None

    await adapter.stop()


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
    assert "broker gone" in (results[0].error or "")

    await adapter.stop()


@pytest.mark.anyio
async def test_committed_multiple_partitions_mixed(mock_aiokafka: MagicMock) -> None:
    call_count = 0

    async def _side_effect(tp: TopicPartition) -> int | None:
        nonlocal call_count
        call_count += 1
        if tp.partition == 0:
            return 100
        return None

    consumer_instance = mock_aiokafka.return_value
    consumer_instance.committed = AsyncMock(side_effect=_side_effect)
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()

    results = await adapter.committed([0, 1])
    assert results[0].status == PositionStatus.VERIFIED
    assert results[0].offset == 100
    assert results[1].status == PositionStatus.ABSENT

    await adapter.stop()


# ---------------------------------------------------------------------------
# End offsets (visible-end boundary)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_end_offsets_verified(mock_aiokafka: MagicMock) -> None:
    tp0 = TopicPartition("events.test", 0)
    tp1 = TopicPartition("events.test", 1)
    consumer_instance = mock_aiokafka.return_value
    consumer_instance.end_offsets = AsyncMock(return_value={tp0: 100, tp1: 200})
    adapter = KafkaPartitionConsumer(_connection(), _source_config())
    await adapter.start()

    results = await adapter.end_offsets([0, 1])
    assert results[0].status == PositionStatus.VERIFIED
    assert results[0].offset == 100
    assert results[1].offset == 200

    await adapter.stop()


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

    await adapter.pause([0, 1], expected_epoch=0)
    consumer_instance.pause.assert_called_once()
    paused_tps = set(consumer_instance.pause.call_args.args)
    assert TopicPartition("t", 0) in paused_tps
    assert TopicPartition("t", 1) in paused_tps

    await adapter.resume([0], expected_epoch=0)
    consumer_instance.resume.assert_called_once()
    resumed_tps = set(consumer_instance.resume.call_args.args)
    assert TopicPartition("t", 0) in resumed_tps

    await adapter.stop()


@pytest.mark.anyio
async def test_pause_rejects_unassigned_partition(mock_aiokafka: MagicMock) -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
    await _start_with_partitions(adapter, mock_aiokafka, {0})

    with pytest.raises(OwnershipRevokedError):
        await adapter.pause([0, 5], expected_epoch=0)

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


def test_sanitize_handles_no_credentials() -> None:
    raw = "Broker not available"
    assert _sanitize(raw) == raw


@pytest.mark.anyio
async def test_start_wraps_kafka_error(mock_aiokafka: MagicMock) -> None:
    mock_aiokafka.return_value.start.side_effect = KafkaConnectionError("Cannot connect password=secret")
    adapter = KafkaPartitionConsumer(_connection(), _source_config())

    with pytest.raises(KafkaTransportError, match="password=\\*\\*\\*"):
        await adapter.start()


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_topic_and_group_id_properties() -> None:
    adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="my.topic", group_id="my.group"))
    assert adapter.topic == "my.topic"
    assert adapter.group_id == "my.group"


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
        conn.security_protocol = "PLAINTEXT"  # type: ignore[misc]


def test_connection_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ResolvedKafkaConnection(
            bootstrap_servers=["b:9092"],
            security_protocol="SSL",
            extra_field="bad",  # type: ignore[call-arg]
        )


def test_connection_has_ssl_context() -> None:
    conn_without = _connection()
    assert not conn_without.has_ssl_context()

    conn_with = ResolvedKafkaConnection(
        bootstrap_servers=["b:9092"],
        security_protocol="SSL",
        ssl_context=ssl.create_default_context(),
    )
    assert conn_with.has_ssl_context()


# ---------------------------------------------------------------------------
# CommittedPositionResult
# ---------------------------------------------------------------------------


def test_position_result_verified_factory() -> None:
    r = CommittedPositionResult.verified(3, 42)
    assert r.partition == 3
    assert r.status == PositionStatus.VERIFIED
    assert r.offset == 42
    assert r.error is None


def test_position_result_absent_factory() -> None:
    r = CommittedPositionResult.absent(1)
    assert r.status == PositionStatus.ABSENT
    assert r.offset is None


def test_position_result_unavailable_factory() -> None:
    r = CommittedPositionResult.unavailable(2, "timeout")
    assert r.status == PositionStatus.UNAVAILABLE
    assert r.error == "timeout"


def test_position_result_frozen() -> None:
    r = CommittedPositionResult.verified(0, 10)
    with pytest.raises(ValidationError):
        r.offset = 20  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RebalanceCallback protocol
# ---------------------------------------------------------------------------


def test_rebalance_callback_protocol_check() -> None:
    class _Good:
        async def on_partitions_assigned(self, partitions: frozenset[int], epoch: int) -> None:
            pass

        async def on_partitions_revoked(self, partitions: frozenset[int], epoch: int) -> None:
            pass

    assert isinstance(_Good(), RebalanceCallback)
