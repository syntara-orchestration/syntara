"""Preflight sends non-creating metadata only and never claims runtime ACLs."""

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokafka.errors import IncompatibleBrokerVersion, KafkaConnectionError
from aiokafka.protocol.metadata import MetadataRequest_v4, MetadataRequest_v5, MetadataResponse_v4, MetadataResponse_v5

from syntara.eventstreams.adapters.kafka_preflight import NonCreatingMetadataRequest
from syntara.eventstreams.adapters.kafka_preflight import test_kafka_connection as preflight
from syntara.integrations.models.integration_configuration import KafkaConfiguration

MODULE = "syntara.eventstreams.adapters.kafka_preflight"
CREDENTIAL = {"kafka_username": "runtime", "kafka_password": "private-value"}
CONFIG = KafkaConfiguration(bootstrap_servers=["broker.example.com:9093"])


@pytest.mark.parametrize("version", [4, 5])
def test_metadata_explicitly_prevents_topic_creation(version: int) -> None:
    """Exercise the actual aiokafka request builder, including encoded bytes."""
    request = NonCreatingMetadataRequest("alerts").prepare({3: (version, version)})
    assert request.allow_auto_topic_creation is False
    assert request.topics == ["alerts"]
    decoded = (MetadataRequest_v4 if version == 4 else MetadataRequest_v5).decode(request.encode())
    assert decoded.allow_auto_topic_creation is False


@pytest.mark.parametrize("versions", [{}, {3: (0, 3)}])
def test_unsafe_metadata_versions_are_rejected(versions: dict[int, tuple[int, int]]) -> None:
    """No downgrade may silently omit the creation-control flag."""
    with pytest.raises((IncompatibleBrokerVersion, NotImplementedError)):
        NonCreatingMetadataRequest("alerts").prepare(versions)


def connection(topics: list[tuple[Any, ...]]) -> MagicMock:
    """Expose only the two allowed network operations."""
    conn = MagicMock(spec=["send", "close"])
    conn.send = AsyncMock(return_value=SimpleNamespace(topics=topics))
    conn.close = AsyncMock()
    return conn


async def test_success_verifies_metadata_but_never_read_or_group_permissions() -> None:
    conn = connection([(0, "alerts", False, [(0, 0, 1, [1], [1], [])])])
    with patch(f"{MODULE}.create_conn", return_value=conn) as create:
        result = await preflight(CONFIG, CREDENTIAL, "alerts")
    assert result.success
    assert result.connection == result.topic_metadata == "verified"
    assert result.topic_read == result.group_access == "unverified"
    assert CREDENTIAL["kafka_password"] not in result.model_dump_json()
    assert create.call_args.kwargs["sasl_plain_username"] == "runtime"
    assert "group_id" not in create.call_args.kwargs
    conn.send.assert_awaited_once()
    request = conn.send.call_args.args[0]
    assert isinstance(request, NonCreatingMetadataRequest)
    assert request.prepare({3: (0, 5)}).allow_auto_topic_creation is False
    conn.close.assert_awaited_once()
    assert [call[0] for call in conn.method_calls] == ["send", "close"]


@pytest.mark.parametrize(
    "topics",
    [[], [(3, "alerts", False, [])], [(29, "alerts", False, [])], [(0, "alerts", False, [(5, 0, -1, [], [], [])])]],
)
async def test_missing_denied_or_unavailable_topic_is_safe(topics: list[tuple[Any, ...]]) -> None:
    conn = connection(topics)
    with patch(f"{MODULE}.create_conn", return_value=conn):
        result = await preflight(CONFIG, CREDENTIAL, "alerts")
    assert not result.success
    assert result.error_code == "topic_metadata_unavailable"
    assert result.topic_metadata == "failed"
    assert result.topic_read == result.group_access == "unverified"
    conn.close.assert_awaited_once()


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (TimeoutError("private-value"), "timeout"),
        (KafkaConnectionError("private-value"), "connection_failed"),
        (IncompatibleBrokerVersion("old"), "safe_metadata_unsupported"),
    ],
)
async def test_failures_are_sanitized_and_close_connections(error: Exception, code: str) -> None:
    conn = connection([])
    conn.send.side_effect = error
    with patch(f"{MODULE}.create_conn", return_value=conn):
        result = await preflight(CONFIG, CREDENTIAL, "alerts")
    assert not result.success
    assert result.error_code == code
    assert "private-value" not in result.model_dump_json()
    conn.close.assert_awaited_once()


@pytest.mark.parametrize(
    "credential",
    [
        {},
        {"kafka_username": "runtime", "kafka_password": " \t"},
        {"kafka_username": " \n", "kafka_password": "private-value"},
        {"kafka_username": None, "kafka_password": "private-value"},
    ],
)
async def test_empty_credentials_never_connect(credential: dict[str, Any]) -> None:
    with patch(f"{MODULE}.create_conn") as create:
        result = await preflight(CONFIG, credential, "alerts")
    assert result.error_code == "authentication_configuration"
    create.assert_not_called()


@pytest.mark.parametrize("version", [4, 5])
@pytest.mark.parametrize("partition_error", [0, 5])
async def test_metadata_parsing_with_real_protocol_responses(version: int, partition_error: int) -> None:
    """v5 adds offline replicas; both versions expose plain tuple entries."""
    response_type = MetadataResponse_v4 if version == 4 else MetadataResponse_v5
    partition: tuple[Any, ...] = (partition_error, 0, 1, [1], [1])
    if version == 5:
        partition += ([],)
    response = response_type(
        throttle_time_ms=0,
        brokers=[(1, "broker.example.com", 9093, None)],
        cluster_id="cluster",
        controller_id=1,
        topics=[(0, "alerts", False, [partition])],
    )
    conn = connection([])
    conn.send.return_value = response_type.decode(response.encode())
    with patch(f"{MODULE}.create_conn", return_value=conn):
        result = await preflight(CONFIG, CREDENTIAL, "alerts")
    assert result.success is (partition_error == 0)
    assert result.topic_metadata == ("verified" if partition_error == 0 else "failed")
    assert result.topic_read == result.group_access == "unverified"


@pytest.mark.parametrize(
    "error", [TimeoutError("private-value"), OSError("private-value"), KafkaConnectionError("private-value")]
)
async def test_close_failures_are_logged_without_secrets_or_changing_result(error: Exception) -> None:
    conn = connection([(0, "alerts", False, [(0, 0, 1, [1], [1], [])])])
    conn.close.side_effect = error
    with patch(f"{MODULE}.create_conn", return_value=conn), patch(f"{MODULE}.logger") as logger:
        result = await preflight(CONFIG, CREDENTIAL, "alerts")
    assert result.success
    logger.debug.assert_called_once_with("Kafka preflight connection close failed", error_type=type(error).__name__)
    assert "private-value" not in str(logger.debug.call_args)


async def test_bootstrap_fallback_is_bounded_and_uses_same_runtime_identity() -> None:
    conn = connection([(0, "alerts", False, [(0, 0, 1, [1], [1], [])])])
    config = KafkaConfiguration(bootstrap_servers=["one.example.com:9093", "two.example.com:9093"])
    with patch(f"{MODULE}.create_conn", side_effect=[KafkaConnectionError(), conn]) as create:
        assert (await preflight(config, CREDENTIAL, "alerts")).success
    assert create.call_count == 2
    assert all(c.kwargs["sasl_plain_username"] == "runtime" for c in create.call_args_list)


async def test_total_deadline_and_cleanup_deadline() -> None:
    conn = connection([])

    async def stalled() -> None:
        await asyncio.Future()

    # A real cancellation exercises timeout enforcement, without a live broker.
    async def blocked_send(*_args: object) -> None:
        await stalled()

    conn.send.side_effect = blocked_send
    conn.close.side_effect = stalled
    with (
        patch(f"{MODULE}.create_conn", return_value=conn),
        patch(f"{MODULE}._PREFLIGHT_TIMEOUT_SECONDS", 0.01),
        patch(f"{MODULE}._CLOSE_TIMEOUT_SECONDS", 0.01),
    ):
        result = await preflight(CONFIG, CREDENTIAL, "alerts")
    assert result.error_code == "timeout"
    conn.close.assert_awaited_once()
