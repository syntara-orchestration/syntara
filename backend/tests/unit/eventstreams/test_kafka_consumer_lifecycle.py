"""Multi-step lifecycle and type contract tests for the Kafka consumer adapter.

Exercises complex rebalance cycles, restart behavior, interleaved operations,
and serialization contracts for shared types. Complements the per-operation
unit tests in ``test_kafka_consumer.py``.
"""

from __future__ import annotations

import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.coordinator.assignors.roundrobin import RoundRobinPartitionAssignor

from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer, _RebalanceListener
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.connection import ResolvedKafkaConnection
from syntara.eventstreams.core.consumer import CommittedPositionResult, PositionStatus
from syntara.eventstreams.exceptions import (
    OwnershipRevokedError,
    StaleEpochError,
)


def _connection() -> ResolvedKafkaConnection:
    return ResolvedKafkaConnection(
        bootstrap_servers=["localhost:9092"],
        security_protocol="PLAINTEXT",
    )


def _source_config(
    topic: str = "lifecycle.test",
    group_id: str = "syntara.life.sub.1",
) -> KafkaSourceConfiguration:
    return KafkaSourceConfiguration(topic=topic, group_id=group_id)


def _patched_consumer() -> tuple[MagicMock, AsyncMock]:
    """Return (patcher context, mock consumer instance)."""
    mock_consumer = AsyncMock()
    mock_consumer.start = AsyncMock()
    mock_consumer.stop = AsyncMock()
    mock_consumer.subscribe = MagicMock()
    mock_consumer.seek = MagicMock()
    mock_consumer.commit = AsyncMock()
    mock_consumer.committed = AsyncMock(return_value=42)
    mock_consumer.end_offsets = AsyncMock(return_value={})
    mock_consumer.pause = MagicMock()
    mock_consumer.resume = MagicMock()
    return mock_consumer


# ---------------------------------------------------------------------------
# Real aiokafka object construction (no broker connection)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_real_consumer_accepts_plaintext_config() -> None:
    """Verify ``AIOKafkaConsumer`` can be constructed with plaintext config."""
    consumer = AIOKafkaConsumer(
        bootstrap_servers=["localhost:9092"],
        client_id="syntara-test",
        group_id="syntara.life.sub.1",
        enable_auto_commit=False,
        auto_offset_reset="none",
        isolation_level="read_committed",
        partition_assignment_strategy=(RoundRobinPartitionAssignor,),
    )
    assert consumer is not None


@pytest.mark.anyio
async def test_real_consumer_accepts_sasl_ssl_config() -> None:
    """Verify ``AIOKafkaConsumer`` can be constructed with SASL_SSL config."""
    ctx = ssl.create_default_context()
    consumer = AIOKafkaConsumer(
        bootstrap_servers=["broker:9093"],
        client_id="syntara-test-ssl",
        group_id="syntara.life.sub.2",
        security_protocol="SASL_SSL",
        sasl_mechanism="SCRAM-SHA-512",
        sasl_plain_username="user",
        sasl_plain_password="pass",  # noqa: S106
        ssl_context=ctx,
        enable_auto_commit=False,
        auto_offset_reset="none",
        isolation_level="read_committed",
        partition_assignment_strategy=(RoundRobinPartitionAssignor,),
    )
    assert consumer is not None


# ---------------------------------------------------------------------------
# Rebalance listener with real aiokafka types
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_rebalance_listener_handles_real_topicpartition_sets() -> None:
    """Verify listener works with real ``TopicPartition`` sets."""
    events: list[tuple[str, frozenset[int], int]] = []

    class _Recorder:
        async def on_partitions_assigned(self, partitions: frozenset[int], epoch: int) -> None:
            events.append(("assigned", partitions, epoch))

        async def on_partitions_revoked(self, partitions: frozenset[int], epoch: int) -> None:
            events.append(("revoked", partitions, epoch))

    adapter = KafkaPartitionConsumer(
        _connection(),
        _source_config(topic="real.topic"),
        rebalance_callback=_Recorder(),
    )
    adapter._running = True

    listener = _RebalanceListener(
        on_revoked=adapter._handle_partitions_revoked,
        on_assigned=adapter._handle_partitions_assigned,
    )

    real_assigned = {TopicPartition("real.topic", 0), TopicPartition("real.topic", 3)}
    await listener.on_partitions_assigned(real_assigned)
    assert adapter.assignment == frozenset({0, 3})
    assert events[-1] == ("assigned", frozenset({0, 3}), 0)

    real_revoked = {TopicPartition("real.topic", 3)}
    await listener.on_partitions_revoked(real_revoked)
    assert adapter.assignment == frozenset({0})
    assert events[-1] == ("revoked", frozenset({3}), 0)


# ---------------------------------------------------------------------------
# Complex lifecycle scenarios
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_epoch_guards_across_full_rebalance_cycle() -> None:
    """Assign -> work -> revoke-all -> reassign; old epoch ops rejected."""
    with patch("syntara.eventstreams.adapters.kafka_consumer.AIOKafkaConsumer") as mock_cls:
        mock_cls.return_value = _patched_consumer()

        adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
        await adapter.start()
        listener = mock_cls.return_value.subscribe.call_args.kwargs["listener"]

        await listener.on_partitions_assigned({TopicPartition("t", p) for p in [0, 1, 2]})
        assert adapter.epoch == 0

        await adapter.seek(0, 100, expected_epoch=0)
        await adapter.commit({0: 101}, expected_epoch=0)
        await adapter.pause([1], expected_epoch=0)
        await adapter.resume([1], expected_epoch=0)

        await listener.on_partitions_revoked({TopicPartition("t", p) for p in [0, 1, 2]})
        assert adapter.epoch == 1
        assert adapter.assignment == frozenset()

        await listener.on_partitions_assigned({TopicPartition("t", 3), TopicPartition("t", 4)})
        assert adapter.assignment == frozenset({3, 4})

        with pytest.raises(StaleEpochError):
            await adapter.seek(3, 0, expected_epoch=0)

        with pytest.raises(OwnershipRevokedError):
            await adapter.seek(0, 0, expected_epoch=1)

        await adapter.seek(3, 50, expected_epoch=1)
        await adapter.commit({3: 51, 4: 10}, expected_epoch=1)

        await adapter.stop()


@pytest.mark.anyio
async def test_restart_preserves_epoch() -> None:
    """After stop + start, epoch carries over; assignment resets."""
    with patch("syntara.eventstreams.adapters.kafka_consumer.AIOKafkaConsumer") as mock_cls:
        mock_cls.return_value = _patched_consumer()

        adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))

        await adapter.start()
        listener = mock_cls.return_value.subscribe.call_args.kwargs["listener"]
        await listener.on_partitions_assigned({TopicPartition("t", 0)})
        await listener.on_partitions_revoked({TopicPartition("t", 0)})
        assert adapter.epoch == 1

        await adapter.stop()
        assert adapter.assignment == frozenset()

        mock_cls.return_value = _patched_consumer()
        await adapter.start()
        assert adapter.is_running
        assert adapter.assignment == frozenset()
        assert adapter.epoch == 1

        await adapter.stop()


@pytest.mark.anyio
async def test_operations_interleaved_with_rebalance() -> None:
    """Mix reads, seeks, commits, pause/resume, and rebalance events."""
    with patch("syntara.eventstreams.adapters.kafka_consumer.AIOKafkaConsumer") as mock_cls:
        mock_consumer = _patched_consumer()
        mock_consumer.committed = AsyncMock(return_value=42)
        mock_consumer.end_offsets = AsyncMock(
            return_value={TopicPartition("t", 0): 100},
        )
        mock_cls.return_value = mock_consumer

        adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"))
        await adapter.start()
        listener = mock_cls.return_value.subscribe.call_args.kwargs["listener"]

        await listener.on_partitions_assigned({TopicPartition("t", 0)})

        committed = await adapter.committed([0])
        assert committed[0].status == PositionStatus.VERIFIED
        assert committed[0].offset == 42

        end = await adapter.end_offsets([0])
        assert end[0].status == PositionStatus.VERIFIED
        assert end[0].offset == 100

        await adapter.seek(0, 42, expected_epoch=0)
        await adapter.commit({0: 43}, expected_epoch=0)

        await adapter.pause([0], expected_epoch=0)

        # empty revoke doesn't bump epoch
        await listener.on_partitions_revoked(set())
        assert adapter.epoch == 0

        await listener.on_partitions_assigned({TopicPartition("t", 0), TopicPartition("t", 1)})
        await adapter.resume([0], expected_epoch=0)
        await adapter.commit({0: 44, 1: 1}, expected_epoch=0)

        await adapter.stop()


@pytest.mark.anyio
async def test_commit_during_revoke_then_epoch_rejected() -> None:
    """Callback can commit revoked partitions; same epoch rejected after."""
    with patch("syntara.eventstreams.adapters.kafka_consumer.AIOKafkaConsumer") as mock_cls:
        mock_consumer = _patched_consumer()
        mock_cls.return_value = mock_consumer

        committed_offsets: dict[int, int] = {}

        class _DrainCallback:
            async def on_partitions_assigned(self, partitions: frozenset[int], epoch: int) -> None:
                pass

            async def on_partitions_revoked(self, partitions: frozenset[int], epoch: int) -> None:
                committed_offsets.update(dict.fromkeys(partitions, 50))
                await adapter.commit(dict.fromkeys(partitions, 50), expected_epoch=epoch)

        adapter = KafkaPartitionConsumer(_connection(), _source_config(topic="t"), rebalance_callback=_DrainCallback())
        await adapter.start()
        listener = mock_cls.return_value.subscribe.call_args.kwargs["listener"]
        await listener.on_partitions_assigned({TopicPartition("t", 0), TopicPartition("t", 1)})

        await listener.on_partitions_revoked({TopicPartition("t", 0), TopicPartition("t", 1)})

        assert committed_offsets == {0: 50, 1: 50}
        mock_consumer.commit.assert_awaited_once()
        assert adapter.epoch == 1

        with pytest.raises(StaleEpochError):
            await adapter.commit({0: 51}, expected_epoch=0)

        await adapter.stop()


# ---------------------------------------------------------------------------
# Type serialization contracts
# ---------------------------------------------------------------------------


def test_position_result_json_roundtrip() -> None:
    original = CommittedPositionResult.verified(5, 1000)
    json_str = original.model_dump_json()
    restored = CommittedPositionResult.model_validate_json(json_str)
    assert restored.partition == 5
    assert restored.status == PositionStatus.VERIFIED
    assert restored.offset == 1000


def test_position_result_absent_serialization() -> None:
    data = CommittedPositionResult.absent(2).model_dump()
    assert data["status"] == "absent"
    assert data["offset"] is None
    assert data["error"] is None


def test_position_result_unavailable_serialization() -> None:
    data = CommittedPositionResult.unavailable(1, "timeout").model_dump()
    assert data["status"] == "unavailable"
    assert data["error"] == "timeout"


def test_connection_with_real_ssl_context() -> None:
    ctx = ssl.create_default_context()
    conn = ResolvedKafkaConnection(
        bootstrap_servers=["broker:9093"],
        security_protocol="SSL",
        ssl_context=ctx,
    )
    assert conn.has_ssl_context()
    assert conn.ssl_context is ctx
    assert "<SSLContext>" in repr(conn)


def test_connection_serialization() -> None:
    conn = _connection()
    data = conn.model_dump()
    assert data["bootstrap_servers"] == ["localhost:9092"]
    assert data["security_protocol"] == "PLAINTEXT"
